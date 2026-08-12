import os
import sys
import re
import json
import uuid
import asyncio
import inspect
import datetime
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Pattern, Set, Tuple, Type

import mcp.types as types
from mcp.server.lowlevel.server import request_ctx
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server
from pydantic import BaseModel, create_model

from nitrostack.core.context import ExecutionContext, TaskContext
from nitrostack.core.decorators import ToolConfig, ResourceConfig, PromptConfig
from nitrostack.core.di import DIContainer
from nitrostack.core.errors import PromptNotFoundError, ResourceNotFoundError
from nitrostack.core.mcp_server import NitroStackMcpServer
from nitrostack.core.pipeline import run_pipeline
from nitrostack.core.additional_decorators import HealthCheckRegistry
from nitrostack.core.task import TaskRegistry
from nitrostack.events.event_emitter import EventEmitter


@dataclass
class ServerConfig:
    name: str
    version: str = "1.0.0"
    transport_type: Optional[str] = None


def mcp_app(module: Type, server: ServerConfig):
    """
    Decorator to declare the main application class.
    Specifies the root AppModule and ServerConfig.
    """
    def decorator(cls: Type):
        cls._mcp_app_module = module
        cls._mcp_app_server = server
        return cls
    return decorator


def get_pydantic_model(schema: Any) -> Type[BaseModel]:
    """Helper to resolve or construct a Pydantic model for input validation."""
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return schema
    if isinstance(schema, dict):
        # Dynamically build a Pydantic model from JSON schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        fields = {}
        for name, prop in properties.items():
            t = Any
            prop_type = prop.get("type")
            if prop_type == "string":
                t = str
            elif prop_type == "integer":
                t = int
            elif prop_type == "number":
                t = float
            elif prop_type == "boolean":
                t = bool
            elif prop_type == "array":
                t = list
            elif prop_type == "object":
                t = dict

            default = ... if name in required else None
            fields[name] = (t, default)
        return create_model("DynamicInputModel", **fields)

    # Return a default empty model if invalid or empty
    return create_model("EmptyInputModel")


@dataclass
class _ToolEntry:
    config: ToolConfig
    input_model: Type[BaseModel]
    instance: Any
    method: Callable


@dataclass
class _ResourceEntry:
    config: ResourceConfig
    instance: Any
    method: Callable
    param_names: List[str] = field(default_factory=list)
    pattern: Optional[Pattern] = None


@dataclass
class _PromptEntry:
    config: PromptConfig
    instance: Any
    method: Callable


class McpApplication:
    def __init__(self, app_class: Type):
        self.app_class = app_class
        if hasattr(app_class, "_mcp_app_module"):
            self.root_module = app_class._mcp_app_module
            self.server_config = app_class._mcp_app_server
        elif hasattr(app_class, "_mcp_module_config"):
            self.root_module = app_class
            self.server_config = ServerConfig(name=app_class._mcp_module_config.name or "mcp-server")
        else:
            raise ValueError("Invalid application class. Must be decorated with @mcp_app or @module.")

        self.mcp_server: Optional[NitroStackMcpServer] = None

        # nitrostack owns these registries directly (no FastMCP-managed tool/resource
        # manager in between) so that any number of low-level `Server` instances can be
        # wired against the same registered tools/resources/prompts (see
        # `create_configured_mcp_server`).
        self._tools: Dict[str, _ToolEntry] = {}
        self._resources: Dict[str, _ResourceEntry] = {}
        self._resource_templates: List[_ResourceEntry] = []
        self._prompts: Dict[str, _PromptEntry] = {}
        self._initial_tools: List[Tuple[Any, Callable, ToolConfig]] = []

        self._bootstrap()

    def _bootstrap(self) -> None:
        # 1. Construct the low-level server directly (no FastMCP)
        self.mcp_server = NitroStackMcpServer(
            name=self.server_config.name,
            version=self.server_config.version,
        )

        # 2. Resolve Module Tree recursively and register services
        resolved_modules: Set[Type] = set()
        self._resolve_modules(self.root_module, resolved_modules)

        container = DIContainer.get_instance()

        # Instantiate all providers and controllers to populate container
        for mod in resolved_modules:
            mod_config = getattr(mod, "_mcp_module_config", None)
            if mod_config:
                # Register & Resolve all providers
                for provider in mod_config.providers:
                    container.resolve(provider)
                # Register & Resolve all controllers
                for controller in mod_config.controllers:
                    container.resolve(controller)

        # 3. Discover decorated methods on all instances in the container
        for token, instance in list(container._instances.items()):
            # Scan members of this instance
            for name, member in inspect.getmembers(instance):
                # Discover Tools
                if hasattr(member, "_mcp_tool_config"):
                    tool_config: ToolConfig = getattr(member, "_mcp_tool_config")
                    self._register_tool(instance, member, tool_config)

                # Discover Resources
                if hasattr(member, "_mcp_resource_config"):
                    resource_config: ResourceConfig = getattr(member, "_mcp_resource_config")
                    self._register_resource(instance, member, resource_config)

                # Discover Prompts
                if hasattr(member, "_mcp_prompt_config"):
                    prompt_config: PromptConfig = getattr(member, "_mcp_prompt_config")
                    self._register_prompt(instance, member, prompt_config)

                # Bind Health Checks
                if hasattr(member, "_mcp_health_check_name"):
                    check_name = getattr(member, "_mcp_health_check_name")
                    HealthCheckRegistry.bind_instance(check_name, member, instance)

                # Bind Event Listeners
                if hasattr(member, "_mcp_event_name"):
                    event_name = getattr(member, "_mcp_event_name")
                    EventEmitter.get_instance().bind_instance(event_name, member, instance)

        # 4. Register Built-in Health check Resource if any checks exist
        if HealthCheckRegistry.get_checks():
            self._register_health_resource()

        # 5. Wire every protocol handler (tools/resources/prompts/tasks/notifications)
        #    onto the owned low-level server. This is factored out so additional server
        #    instances (e.g. one per HTTP session) can be configured identically.
        self._setup_handlers(self.mcp_server)

    def _resolve_modules(self, module_class: Type, resolved_modules: Set[Type]) -> None:
        if module_class in resolved_modules:
            return
        resolved_modules.add(module_class)

        mod_config = getattr(module_class, "_mcp_module_config", None)
        if mod_config:
            for imp in mod_config.imports:
                self._resolve_modules(imp, resolved_modules)

    # ------------------------------------------------------------------
    # Registration (pure bookkeeping — no protocol/server calls here)
    # ------------------------------------------------------------------

    def _register_tool(self, instance: Any, method: Callable, tool_config: ToolConfig) -> None:
        input_model = get_pydantic_model(tool_config.input_schema)
        entry = _ToolEntry(config=tool_config, input_model=input_model, instance=instance, method=method)
        self._tools[tool_config.name] = entry
        if tool_config.is_initial:
            self._initial_tools.append((instance, method, tool_config))

    def _register_resource(self, instance: Any, method: Callable, resource_config: ResourceConfig) -> None:
        param_names = re.findall(r"\{([^}]+)\}", resource_config.uri)
        entry = _ResourceEntry(config=resource_config, instance=instance, method=method, param_names=param_names)

        if param_names:
            # Build a matching regex from the URI template, e.g. "a://b/{id}" ->
            # "^a://b/(?P<id>[^/]+)$", preserving the existing template-matching semantics.
            regex_str = re.escape(resource_config.uri)
            for pname in param_names:
                regex_str = regex_str.replace(re.escape("{" + pname + "}"), f"(?P<{pname}>[^/]+)")
            entry.pattern = re.compile(f"^{regex_str}$")
            self._resource_templates.append(entry)
        else:
            self._resources[resource_config.uri] = entry

    def _register_prompt(self, instance: Any, method: Callable, prompt_config: PromptConfig) -> None:
        self._prompts[prompt_config.name] = _PromptEntry(config=prompt_config, instance=instance, method=method)

    def _register_health_resource(self) -> None:
        config = ResourceConfig(
            uri="health://status",
            name="Health Status",
            description="System health status check",
        )

        async def health_status_resource(context: ExecutionContext) -> str:
            results = HealthCheckRegistry.run_all()
            return json.dumps(results)

        self._resources[config.uri] = _ResourceEntry(config=config, instance=None, method=health_status_resource)

    # ------------------------------------------------------------------
    # Protocol handler wiring (owned low-level `mcp.server.lowlevel.Server`)
    # ------------------------------------------------------------------

    def _setup_handlers(self, server: NitroStackMcpServer) -> None:
        @server.list_tools()
        async def _list_tools() -> List[types.Tool]:
            return [self._build_tool_definition(entry) for entry in self._tools.values()]

        @server.call_tool()
        async def _call_tool(name: str, arguments: Optional[Dict[str, Any]]):
            return await self._call_tool(name, arguments or {})

        @server.list_resources()
        async def _list_resources() -> List[types.Resource]:
            return [self._build_resource_definition(entry) for entry in self._resources.values()]

        @server.list_resource_templates()
        async def _list_resource_templates() -> List[types.ResourceTemplate]:
            return [self._build_resource_template_definition(entry) for entry in self._resource_templates]

        @server.read_resource()
        async def _read_resource(uri: Any):
            return await self._read_resource(str(uri))

        @server.subscribe_resource()
        async def _subscribe_resource(uri: Any) -> None:
            if str(uri) not in self._resources:
                raise ResourceNotFoundError(str(uri))

        @server.unsubscribe_resource()
        async def _unsubscribe_resource(uri: Any) -> None:
            return None

        @server.list_prompts()
        async def _list_prompts() -> List[types.Prompt]:
            return [self._build_prompt_definition(entry) for entry in self._prompts.values()]

        @server.get_prompt()
        async def _get_prompt(name: str, arguments: Optional[Dict[str, str]]) -> types.GetPromptResult:
            return await self._get_prompt(name, arguments or {})

        self._register_task_handlers(server)
        self._register_initialized_handler(server)

    def create_configured_mcp_server(self) -> NitroStackMcpServer:
        """
        Build a fresh, fully-wired low-level server instance sharing this
        application's tool/resource/prompt registries. A single shared server is
        sufficient for the Python `mcp` SDK's HTTP session managers (unlike the TS
        SDK's `Server`, `.run()` here does not bind a transport for the instance's
        lifetime), but this factory is kept available for isolated/stateless use
        cases (e.g. Phase 3 extensions) that want their own server instance.
        """
        server = NitroStackMcpServer(name=self.server_config.name, version=self.server_config.version)
        self._setup_handlers(server)
        return server

    # ------------------------------------------------------------------
    # Definition builders (registry entry -> wire-level `mcp.types` objects)
    # ------------------------------------------------------------------

    def _wrap_tool_input_schema(self, input_schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Wrap a Pydantic model JSON schema under `{"input": ...}` the way FastMCP
        (and NitroStudio) expect.

        Studio's form generator resolves `properties.input.$ref` against `$defs`
        to render individual fields. Inlining the model under `properties.input`
        makes Studio treat it as a single JSON-object blob — so we always emit the
        `$ref` + `$defs` shape (matching FastMCP's previous wire contract).
        """
        nested_defs = dict(input_schema.get("$defs") or input_schema.get("definitions") or {})
        model_schema = {k: v for k, v in input_schema.items() if k not in ("$defs", "definitions")}
        model_name = model_schema.get("title") or "Input"
        # Avoid colliding with an existing nested def of the same name
        if model_name in nested_defs:
            model_name = f"{model_name}Input"

        return {
            "type": "object",
            "title": f"{model_name}Arguments",
            "properties": {"input": {"$ref": f"#/$defs/{model_name}"}},
            "required": ["input"],
            "$defs": {**nested_defs, model_name: model_schema},
        }

    def _build_tool_definition(self, entry: _ToolEntry) -> types.Tool:
        cfg = entry.config
        wrapped_schema = self._wrap_tool_input_schema(entry.input_model.model_json_schema())

        meta: Dict[str, Any] = {
            "is_initial": cfg.is_initial,
            "visibility": cfg.visibility,
            "task_support": cfg.task_support,
            **(cfg.metadata or {}),
        }
        widget_route = getattr(entry.method, "_mcp_widget", None)
        if widget_route:
            meta["ui/template"] = widget_route
            meta["ui"] = {"resourceUri": widget_route}
            meta["openai/outputTemplate"] = widget_route
        if cfg.invocation:
            meta["openai/toolInvocation/invoking"] = cfg.invocation.invoking
            meta["openai/toolInvocation/invoked"] = cfg.invocation.invoked
        if cfg.examples:
            meta["examples"] = {
                "input": cfg.examples.input,
                "output": cfg.examples.output,
                "description": cfg.examples.description,
            }

        app_mode = os.environ.get("NITROSTACK_APP_MODE", "mcp")
        if app_mode == "openai":
            meta["openai/type"] = "function"
            meta["openai/function"] = {
                "name": cfg.name,
                "description": cfg.description,
                "parameters": wrapped_schema,
            }
        elif app_mode == "mcpapps":
            meta["_meta"] = {"ui": {"title": cfg.title or cfg.name, "description": cfg.description}}

        annotations = types.ToolAnnotations(
            readOnlyHint=cfg.annotations.read_only_hint,
            destructiveHint=cfg.annotations.destructive_hint,
            idempotentHint=cfg.annotations.idempotent_hint,
            openWorldHint=cfg.annotations.open_world_hint,
        )

        execution = None
        if cfg.task_support and cfg.task_support != "forbidden":
            execution = types.ToolExecution(taskSupport=cfg.task_support)

        return types.Tool(
            name=cfg.name,
            title=cfg.title,
            description=cfg.description,
            inputSchema=wrapped_schema,
            annotations=annotations,
            execution=execution,
            **{"_meta": meta},
        )

    def _build_resource_definition(self, entry: _ResourceEntry) -> types.Resource:
        cfg = entry.config
        return types.Resource(
            uri=cfg.uri,
            name=cfg.name,
            title=cfg.title,
            description=cfg.description,
            mimeType=cfg.mime_type,
            size=cfg.size,
        )

    def _build_resource_template_definition(self, entry: _ResourceEntry) -> types.ResourceTemplate:
        cfg = entry.config
        return types.ResourceTemplate(
            uriTemplate=cfg.uri,
            name=cfg.name,
            title=cfg.title,
            description=cfg.description,
            mimeType=cfg.mime_type,
        )

    def _build_prompt_definition(self, entry: _PromptEntry) -> types.Prompt:
        cfg = entry.config
        arguments = [
            types.PromptArgument(name=arg.name, description=arg.description, required=arg.required)
            for arg in cfg.arguments
        ]
        return types.Prompt(name=cfg.name, description=cfg.description, arguments=arguments or None)

    # ------------------------------------------------------------------
    # Request dispatch
    # ------------------------------------------------------------------

    def _pipeline_stages(self, method: Callable) -> Tuple[List[Type], List[Type], List[Type], List[Type], List[Type]]:
        return (
            getattr(method, "_mcp_guards", []),
            getattr(method, "_mcp_middleware", []),
            getattr(method, "_mcp_interceptors", []),
            getattr(method, "_mcp_pipes", []),
            getattr(method, "_mcp_filters", []),
        )

    @staticmethod
    def _to_call_tool_result(result: Any) -> types.CallToolResult:
        if isinstance(result, types.CallToolResult):
            return result
        if isinstance(result, BaseModel):
            result = result.model_dump()
        if isinstance(result, dict):
            if "content" in result and "isError" in result:
                return types.CallToolResult(**result)
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))],
                structuredContent=result,
                isError=False,
            )
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=str(result))],
            isError=False,
        )

    async def _call_tool(self, name: str, arguments: Dict[str, Any]):
        entry = self._tools.get(name)
        if entry is None:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=f"Tool '{name}' not found")],
                isError=True,
            )

        cfg = entry.config
        input_instance = entry.input_model.model_validate(arguments.get("input", {}))
        guards, middleware, interceptors, pipes, filters = self._pipeline_stages(entry.method)

        # Detect task-augmented invocation via the request context's public
        # `experimental.task_metadata` field (populated by the low-level server
        # from `req.params.task`) rather than reaching into private state.
        task_metadata = None
        rc = request_ctx.get(None)
        if rc is not None and getattr(rc, "experimental", None) is not None:
            task_metadata = rc.experimental.task_metadata

        is_task = (task_metadata is not None) or (cfg.task_support == "required")
        if cfg.task_support == "forbidden":
            is_task = False

        if is_task:
            task_id = f"task_{uuid.uuid4().hex[:12]}"
            ttl = task_metadata.ttl if task_metadata else 300
            TaskRegistry.create_task(task_id, ttl=ttl)

            async def background_execution():
                task_ctx = ExecutionContext(
                    request_id=str(uuid.uuid4()),
                    tool_name=cfg.name,
                    metadata={"input": input_instance},
                )
                task_ctx.task = TaskContext(task_id)
                try:
                    result = await run_pipeline(
                        handler=entry.method,
                        handler_instance=entry.instance,
                        args=(input_instance, task_ctx),
                        kwargs={},
                        context=task_ctx,
                        guards=guards,
                        middleware=middleware,
                        interceptors=interceptors,
                        pipes=pipes,
                        filters=filters,
                        param_name="input",
                        param_type=entry.input_model,
                    )
                    TaskRegistry.complete_task(task_id, self._to_call_tool_result(result))
                except Exception as e:
                    TaskRegistry.fail_task(task_id, e)

            asyncio.create_task(background_execution())
            now = datetime.datetime.now(datetime.timezone.utc)
            return types.CreateTaskResult(
                task=types.Task(
                    taskId=task_id,
                    status="working",
                    statusMessage="Task started",
                    createdAt=now,
                    lastUpdatedAt=now,
                    ttl=ttl,
                    pollInterval=5,
                )
            )

        ctx = ExecutionContext(request_id=str(uuid.uuid4()), tool_name=cfg.name, metadata={"input": input_instance})
        result = await run_pipeline(
            handler=entry.method,
            handler_instance=entry.instance,
            args=(input_instance, ctx),
            kwargs={},
            context=ctx,
            guards=guards,
            middleware=middleware,
            interceptors=interceptors,
            pipes=pipes,
            filters=filters,
            param_name="input",
            param_type=entry.input_model,
        )
        return self._to_call_tool_result(result)

    async def _read_resource(self, uri: str) -> List[ReadResourceContents]:
        entry = self._resources.get(uri)
        path_kwargs: Dict[str, str] = {}

        if entry is None:
            for template_entry in self._resource_templates:
                match = template_entry.pattern.match(uri) if template_entry.pattern else None
                if match:
                    entry = template_entry
                    path_kwargs = match.groupdict()
                    break

        if entry is None:
            raise ResourceNotFoundError(uri)

        cfg = entry.config
        ctx = ExecutionContext(request_id=str(uuid.uuid4()), metadata=dict(path_kwargs))
        guards, middleware, interceptors, pipes, filters = self._pipeline_stages(entry.method)

        result = await run_pipeline(
            handler=entry.method,
            handler_instance=entry.instance,
            args=(),
            kwargs={**path_kwargs, "context": ctx},
            context=ctx,
            guards=guards,
            middleware=middleware,
            interceptors=interceptors,
            pipes=pipes,
            filters=filters,
        )

        # Support Discriminated Union formats for return (Section 1.2)
        if isinstance(result, dict) and "type" in result and "data" in result:
            result = result["data"]

        if isinstance(result, BaseModel):
            result = result.model_dump()

        if isinstance(result, bytes):
            return [ReadResourceContents(content=result, mime_type=cfg.mime_type or "application/octet-stream")]

        if isinstance(result, str):
            return [ReadResourceContents(content=result, mime_type=cfg.mime_type or "text/plain")]

        text = json.dumps(result, indent=2, default=str)
        return [ReadResourceContents(content=text, mime_type=cfg.mime_type or "application/json")]

    async def _get_prompt(self, name: str, arguments: Dict[str, str]) -> types.GetPromptResult:
        entry = self._prompts.get(name)
        if entry is None:
            raise PromptNotFoundError(name)

        cfg = entry.config
        args_dict = dict(arguments or {})
        ctx = ExecutionContext(request_id=str(uuid.uuid4()), metadata=args_dict)
        guards, middleware, interceptors, pipes, filters = self._pipeline_stages(entry.method)

        raw_messages = await run_pipeline(
            handler=entry.method,
            handler_instance=entry.instance,
            args=(args_dict, ctx),
            kwargs={},
            context=ctx,
            guards=guards,
            middleware=middleware,
            interceptors=interceptors,
            pipes=pipes,
            filters=filters,
        )

        if not isinstance(raw_messages, (list, tuple)):
            raw_messages = [raw_messages]

        messages: List[types.PromptMessage] = []
        for msg in raw_messages:
            role = msg.role if hasattr(msg, "role") else msg.get("role")
            content = msg.content if hasattr(msg, "content") else msg.get("content")
            messages.append(types.PromptMessage(role=role, content=types.TextContent(type="text", text=content)))

        return types.GetPromptResult(description=cfg.description, messages=messages)

    # ------------------------------------------------------------------
    # Task subsystem — registered directly on the low-level server's public
    # `request_handlers`/`notification_handlers` dicts (no FastMCP reach-through).
    # ------------------------------------------------------------------

    def _register_task_handlers(self, server: NitroStackMcpServer) -> None:
        async def handle_list_tasks(req):
            tasks_list = [
                types.Task(
                    taskId=t.task_id,
                    status=t.status,
                    statusMessage=t.status_message,
                    createdAt=t.created_at,
                    lastUpdatedAt=t.last_updated_at,
                    ttl=t.ttl,
                    pollInterval=t.poll_interval,
                )
                for t in TaskRegistry.list_tasks()
            ]
            return types.ListTasksResult(tasks=tasks_list, nextCursor=None)

        async def handle_get_task(req):
            task_id = req.params.taskId
            t = TaskRegistry.get_task(task_id)
            if not t:
                raise types.McpError(
                    types.ErrorData(code=types.INVALID_PARAMS, message=f"Task {task_id} not found")
                )
            return types.GetTaskResult(
                taskId=t.task_id,
                status=t.status,
                statusMessage=t.status_message,
                createdAt=t.created_at,
                lastUpdatedAt=t.last_updated_at,
                ttl=t.ttl,
                pollInterval=t.poll_interval,
            )

        async def handle_cancel_task(req):
            task_id = req.params.taskId
            t = TaskRegistry.get_task(task_id)
            if not t:
                raise types.McpError(
                    types.ErrorData(code=types.INVALID_PARAMS, message=f"Task {task_id} not found")
                )
            TaskRegistry.cancel_task(task_id)
            t = TaskRegistry.get_task(task_id)
            return types.CancelTaskResult(
                taskId=t.task_id,
                status=t.status,
                statusMessage=t.status_message,
                createdAt=t.created_at,
                lastUpdatedAt=t.last_updated_at,
                ttl=t.ttl,
                pollInterval=t.poll_interval,
            )

        async def handle_get_task_payload(req):
            task_id = req.params.taskId
            t = TaskRegistry.get_task(task_id)
            if not t:
                raise types.McpError(
                    types.ErrorData(code=types.INVALID_PARAMS, message=f"Task {task_id} not found")
                )
            await t.done_event.wait()
            if t.status == "completed":
                return t.result
            elif t.status == "cancelled":
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text="Task was cancelled.")],
                    isError=True,
                )
            else:
                return types.CallToolResult(
                    content=[types.TextContent(type="text", text=str(t.error or t.status_message))],
                    isError=True,
                )

        server.request_handlers[types.ListTasksRequest] = handle_list_tasks
        server.request_handlers[types.GetTaskRequest] = handle_get_task
        server.request_handlers[types.CancelTaskRequest] = handle_cancel_task
        server.request_handlers[types.GetTaskPayloadRequest] = handle_get_task_payload
        server.has_task_support = True

    def _register_initialized_handler(self, server: NitroStackMcpServer) -> None:
        async def handle_initialized(notification: types.InitializedNotification):
            for instance, method, config in self._initial_tools:
                try:
                    entry = self._tools[config.name]
                    try:
                        input_inst = entry.input_model()
                    except Exception:
                        input_inst = None

                    ctx = ExecutionContext(
                        request_id=f"initial-tool-{uuid.uuid4().hex[:8]}",
                        tool_name=config.name,
                        metadata={},
                    )
                    guards, middleware, interceptors, pipes, filters = self._pipeline_stages(method)

                    await run_pipeline(
                        handler=method,
                        handler_instance=instance,
                        args=(input_inst, ctx),
                        kwargs={},
                        context=ctx,
                        guards=guards,
                        middleware=middleware,
                        interceptors=interceptors,
                        pipes=pipes,
                        filters=filters,
                        param_name="input",
                        param_type=entry.input_model,
                    )
                except Exception as e:
                    sys.stderr.write(f"Error executing initial tool '{config.name}': {e}\n")
                    sys.stderr.flush()

        server.notification_handlers[types.InitializedNotification] = handle_initialized

    # ------------------------------------------------------------------
    # Transports
    # ------------------------------------------------------------------

    def get_combined_app(self) -> Any:
        """
        Minimal Starlette app wiring the owned low-level server directly to both the
        modern Streamable HTTP transport (`/mcp`) and the legacy SSE transport
        (`/sse` + `/mcp/messages`). Full session lifecycle management, auth
        middleware, and dual-mode orchestration are Phase 3's job — this is the
        foundation it extends.
        """
        import contextlib
        from starlette.applications import Starlette
        from starlette.routing import Mount, Route
        from starlette.responses import Response
        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        from mcp.server.sse import SseServerTransport

        session_manager = StreamableHTTPSessionManager(app=self.mcp_server, stateless=False)
        sse_transport = SseServerTransport("/mcp/messages")

        async def handle_streamable_http(scope, receive, send) -> None:
            await session_manager.handle_request(scope, receive, send)

        async def handle_sse(request):
            async with sse_transport.connect_sse(request.scope, request.receive, request._send) as streams:
                await self.mcp_server.run(streams[0], streams[1], self.mcp_server.create_initialization_options())
            return Response()

        @contextlib.asynccontextmanager
        async def lifespan(app):
            async with session_manager.run():
                yield

        return Starlette(
            routes=[
                # `handle_streamable_http` and `handle_post_message` are raw ASGI apps
                # (scope, receive, send), so they must be `Mount`ed rather than used as
                # `Route` endpoints (which expect a `Request -> Response` function).
                Mount("/mcp", app=handle_streamable_http),
                Route("/sse", endpoint=handle_sse, methods=["GET"]),
                Mount("/mcp/messages", app=sse_transport.handle_post_message),
            ],
            lifespan=lifespan,
        )

    async def _run_stdio(self) -> None:
        async with stdio_server() as (read_stream, write_stream):
            await self.mcp_server.run(read_stream, write_stream, self.mcp_server.create_initialization_options())

    async def start(self) -> None:
        """Starts the MCP application based on transport configurations."""
        # Start background OAuth discovery server if OAuthService is resolved
        try:
            from nitrostack.auth.oauth import OAuthService
            oauth_service = DIContainer.get_instance().resolve(OAuthService)
            oauth_service.start_discovery_server()
        except Exception:
            pass

        transport = os.environ.get("MCP_TRANSPORT_TYPE") or getattr(self.server_config, "transport_type", None)
        node_env = os.environ.get("NODE_ENV", "development")
        port = int(os.environ.get("PORT") or os.environ.get("MCP_SERVER_PORT") or 8000)

        if transport == "http":
            # Run combined HTTP Server
            import uvicorn
            app = self.get_combined_app()
            config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="info")
            server = uvicorn.Server(config)
            await server.serve()
        elif transport == "dual" or (node_env == "production" and not transport):
            # dual mode: stdio + HTTP
            import threading

            def run_http():
                import asyncio as _asyncio
                import uvicorn
                loop = _asyncio.new_event_loop()
                _asyncio.set_event_loop(loop)
                app = self.get_combined_app()
                config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
                server = uvicorn.Server(config)
                loop.run_until_complete(server.serve())

            http_thread = threading.Thread(target=run_http, daemon=True)
            http_thread.start()

            # Run stdio in the main thread
            from nitrostack.transports.stdio import safe_stdio_transport
            with safe_stdio_transport():
                await self._run_stdio()
        else:
            # Default Stdio
            from nitrostack.transports.stdio import safe_stdio_transport
            with safe_stdio_transport():
                await self._run_stdio()


class McpApplicationFactory:
    @classmethod
    async def create(cls, app_class: Type) -> McpApplication:
        """Bootstraps and instantiates the McpApplication class."""
        return McpApplication(app_class)
