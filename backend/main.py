from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import json
from graph_service import graph_service
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="SimpleGraphRAG Backend API")

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TaskSubmit(BaseModel):
    input_text: str


class TaskInfo(BaseModel):
    task_id: str
    status: str
    input_text: str
    created_at: Optional[str]
    duration: Optional[float]
    error: Optional[str]


# System 管理相关的请求模型
class ClassCreate(BaseModel):
    class_name: str
    description: str
    properties: List[dict]


class ClassUpdate(BaseModel):
    description: Optional[str] = None
    properties: Optional[List[dict]] = None


class PropertyAdd(BaseModel):
    property_name: str
    description: Optional[str] = None
    required: bool = False
    value_required: bool = False


# Entity 管理相关的请求模型
class EntityUpdate(BaseModel):
    description: Optional[str] = None
    add_classes: Optional[List[str]] = None
    remove_classes: Optional[List[str]] = None


class PropertyUpdate(BaseModel):
    class_name: str
    property_name: str
    value: str


class ClassAddToEntity(BaseModel):
    class_name: str
    properties: Optional[dict] = None


@app.on_event("startup")
async def startup_event():
    await graph_service.initialize()


@app.on_event("shutdown")
async def shutdown_event():
    await graph_service.shutdown()


@app.post("/api/tasks", response_model=dict)
async def submit_task(task: TaskSubmit):
    task_id = await graph_service.submit_task(task.input_text)
    return {"task_id": task_id}


@app.get("/api/tasks", response_model=List[dict])
async def list_tasks():
    return graph_service.get_all_tasks()


@app.get("/api/tasks/{task_id}", response_model=dict)
async def get_task(task_id: str):
    status = graph_service.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found")
    return status


@app.get("/api/tasks/{task_id}/delta", response_model=dict)
async def get_task_delta(task_id: str):
    """获取任务的增量数据"""
    delta_info = graph_service.get_task_delta(task_id)
    if not delta_info:
        raise HTTPException(status_code=404, detail="Task not found")
    return delta_info


@app.get("/api/tasks/{task_id}/stages", response_model=dict)
async def get_task_stage_details(task_id: str):
    """获取任务各阶段的详细数据（包括输入、输出、LLM响应）"""
    stage_details = graph_service.get_task_stage_details(task_id)
    if not stage_details:
        raise HTTPException(status_code=404, detail="Task not found")
    return stage_details


@app.get("/api/graph", response_model=dict)
async def get_graph():
    return graph_service.get_graph_data()


@app.get("/api/stats", response_model=dict)
async def get_stats():
    return graph_service.get_stats()


@app.get("/api/events")
async def events():
    """SSE 进度事件推送"""

    async def event_generator():
        try:
            while True:
                # 获取进度更新
                event = await graph_service.task_events.get()

                # 确保事件包含必要字段
                if "event_type" not in event:
                    event["event_type"] = "progress"

                # 发送事件
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                graph_service.task_events.task_done()

                # 添加心跳以保持连接
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            # 客户端断开连接
            pass
        except Exception as e:
            print(f"SSE error: {e}")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ========== System 管理 API ==========


@app.get("/api/system/classes", response_model=List[dict])
async def get_system_classes():
    """获取所有类定义"""
    return graph_service.get_system_classes()


@app.get("/api/system/classes/{class_name}", response_model=dict)
async def get_class_definition(class_name: str):
    """获取指定类的定义"""
    class_def = graph_service.get_class_definition(class_name)
    if not class_def:
        raise HTTPException(status_code=404, detail=f"Class '{class_name}' not found")
    return class_def


@app.post("/api/system/classes", response_model=dict)
async def add_class(class_data: ClassCreate):
    """添加新类到System"""
    try:
        return graph_service.add_class_to_system(
            class_name=class_data.class_name,
            description=class_data.description,
            properties=class_data.properties,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/system/classes/{class_name}", response_model=dict)
async def update_class(class_name: str, class_data: ClassUpdate):
    """更新类定义（只能增强，不能删除）"""
    try:
        return graph_service.update_class_definition(
            class_name=class_name,
            description=class_data.description,
            properties=class_data.properties,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/system/classes/{class_name}/properties", response_model=dict)
async def add_property(class_name: str, property_data: PropertyAdd):
    """向类添加新属性"""
    try:
        return graph_service.add_property_to_class(
            class_name=class_name,
            property_name=property_data.property_name,
            description=property_data.description,
            required=property_data.required,
            value_required=property_data.value_required,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========== Entity 管理 API ==========


@app.get("/api/entities", response_model=List[dict])
async def get_all_entities():
    """获取所有实体的摘要信息"""
    return graph_service.get_all_entities()


@app.get("/api/entities/{entity_name}", response_model=dict)
async def get_entity_detail(entity_name: str):
    """获取实体的详细信息"""
    entity = graph_service.get_entity_detail(entity_name)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_name}' not found")
    return entity


@app.put("/api/entities/{entity_name}", response_model=dict)
async def update_entity(entity_name: str, entity_data: EntityUpdate):
    """更新实体信息"""
    try:
        return graph_service.update_entity(
            entity_name=entity_name,
            description=entity_data.description,
            add_classes=entity_data.add_classes,
            remove_classes=entity_data.remove_classes,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/entities/{entity_name}/properties", response_model=dict)
async def update_entity_property(entity_name: str, property_data: PropertyUpdate):
    """更新实体的属性值"""
    try:
        return graph_service.update_entity_property(
            entity_name=entity_name,
            class_name=property_data.class_name,
            property_name=property_data.property_name,
            value=property_data.value,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/entities/{entity_name}/classes", response_model=dict)
async def add_class_to_entity(entity_name: str, class_data: ClassAddToEntity):
    """为实体添加新类及其属性值"""
    try:
        return graph_service.add_class_to_entity(
            entity_name=entity_name,
            class_name=class_data.class_name,
            properties=class_data.properties,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ========== 查询 API ==========


class SearchQuery(BaseModel):
    keyword: str
    fuzzy: bool = True
    limit: Optional[int] = 50


@app.post("/api/search/keyword", response_model=List[dict])
async def search_keyword(query: SearchQuery):
    """
    关键词查询

    支持在实体、关系、类、属性等所有可检索内容中搜索

    Args:
        keyword: 关键词
        fuzzy: 是否模糊查询（True=模糊，False=严格匹配）
        limit: 结果数量限制（默认50）

    Returns:
        搜索结果列表，每个结果包含：
        - result_type: 结果类型（entity/class_node/relationship等）
        - matched_text: 匹配到的文本
        - context: 上下文信息
        - score: 相关度得分（0-1）
    """
    try:
        results = graph_service.search_keyword(query.keyword, query.fuzzy, query.limit)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@app.get("/api/search/node/{node_id:path}", response_model=dict)
async def get_node_detail(node_id: str):
    """
    查询节点详细信息（含一层连接）

    Args:
        node_id: 节点ID，可以是：
            - 实体名称（如"小红书"）
            - 类节点ID（如"小红书:购物平台"）
            - 类主节点名称（如"购物平台"）

    Returns:
        节点详细信息，包含：
        - node_id: 节点ID
        - node_type: 节点类型（entity/class_node/class_master_node）
        - node_info: 节点本身的信息
        - one_hop_relationships: 一层连接的关系列表
        - one_hop_neighbors: 一层邻居节点列表
        - statistics: 统计信息
    """
    node_detail = graph_service.get_node_detail(node_id)
    if not node_detail:
        raise HTTPException(status_code=404, detail=f"Node '{node_id}' not found")
    return node_detail


@app.get("/api/search/entity-group/{entity_name}", response_model=dict)
async def get_entity_node_group(entity_name: str):
    """
    查询实体节点组（实体 + 其下所有实体类节点 + 一层连接）

    Args:
        entity_name: 实体名称

    Returns:
        实体节点组，包含：
        - entity: 实体节点信息（包含所有属性）
        - class_nodes: 实体的所有类节点列表
        - one_hop_relationships: 一层连接的关系列表（包括实体和类节点的关系）
        - statistics: 统计信息
    """
    entity_group = graph_service.get_entity_node_group(entity_name)
    if not entity_group:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_name}' not found")
    return entity_group


@app.get("/api/search/class-group/{class_name}", response_model=dict)
async def get_class_node_group(class_name: str):
    """
    查询类节点组（类主节点 + 所有实例化该类的实体类节点 + 一层连接）

    Args:
        class_name: 类名称

    Returns:
        类节点组，包含：
        - class_master_node: 类主节点信息
        - class_nodes: 所有实例化该类的实体类节点列表
        - one_hop_relationships: 一层连接的关系列表
        - statistics: 统计信息
    """
    class_group = graph_service.get_class_node_group(class_name)
    if not class_group:
        raise HTTPException(status_code=404, detail=f"Class '{class_name}' not found")
    return class_group


# ========== 数据库管理 API ==========


class DatabaseSaveRequest(BaseModel):
    file_name: Optional[str] = None  # 文件名（可选，不指定则使用默认）


class DatabaseLoadRequest(BaseModel):
    file_name: Optional[str] = None  # 文件名（可选，不指定则使用默认）


class AutoSaveConfig(BaseModel):
    enabled: bool


class DatabaseCreateRequest(BaseModel):
    file_name: Optional[str] = None  # 文件名（可选）


class DatabaseDeleteRequest(BaseModel):
    file_name: str  # 要删除的文件名


class DatabaseRenameRequest(BaseModel):
    old_name: str  # 旧文件名
    new_name: str  # 新文件名


@app.post("/api/database/create", response_model=dict)
async def create_new_database(request: DatabaseCreateRequest):
    """
    创建新的空数据库

    Args:
        file_name: 文件名（可选），如果不指定则使用默认文件名

    Returns:
        创建结果信息，包含：
        - success: 是否成功
        - file_path: 文件路径
        - file_name: 文件名
        - statistics: 数据库统计信息
        - message: 提示消息
    """
    try:
        result = await graph_service.create_new_database(request.file_name)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/database/save", response_model=dict)
async def save_database(request: DatabaseSaveRequest):
    """
    保存数据库到文件

    Args:
        file_name: 文件名（可选），如果不指定则使用默认文件名

    Returns:
        保存结果信息，包含：
        - success: 是否成功
        - file_path: 保存的文件路径
        - file_size: 文件大小（字节）
        - statistics: 数据库统计信息
        - message: 提示消息
    """
    try:
        file_path = None
        if request.file_name:
            from pathlib import Path

            file_path = graph_service.data_dir / request.file_name

        result = await graph_service.save_database(file_path)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/database/load", response_model=dict)
async def load_database(request: DatabaseLoadRequest):
    """
    从文件加载数据库

    Args:
        file_name: 文件名（可选），如果不指定则使用默认文件名

    Returns:
        加载结果信息，包含：
        - success: 是否成功
        - file_path: 加载的文件路径
        - file_size: 文件大小（字节）
        - statistics: 数据库统计信息
        - message: 提示消息
    """
    try:
        file_path = None
        if request.file_name:
            from pathlib import Path

            file_path = graph_service.data_dir / request.file_name

        result = await graph_service.load_database(file_path)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/database/list", response_model=List[dict])
async def list_databases():
    """
    列出所有可用的数据库文件

    Returns:
        数据库文件列表，每个包含：
        - file_name: 文件名
        - file_path: 完整路径
        - file_size: 文件大小（字节）
        - modified_time: 最后修改时间（Unix时间戳）
        - is_default: 是否为默认数据库文件
    """
    try:
        databases = await graph_service.list_database_files()
        return databases
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/database/auto-save", response_model=dict)
async def set_auto_save(config: AutoSaveConfig):
    """
    设置是否启用自动保存

    Args:
        enabled: 是否启用自动保存

    Returns:
        配置结果
    """
    try:
        graph_service.set_auto_save(config.enabled)
        return {
            "success": True,
            "auto_save_enabled": config.enabled,
            "message": f"自动保存已{'启用' if config.enabled else '禁用'}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/database/status", response_model=dict)
async def get_database_status():
    """
    获取数据库状态信息

    Returns:
        数据库状态，包含：
        - initialized: 是否已初始化
        - default_path: 默认数据库路径
        - auto_save_enabled: 是否启用自动保存
        - statistics: 当前图谱统计信息
    """
    try:
        status = {
            "initialized": graph_service.sg is not None,
            "default_path": str(graph_service.get_default_database_path()),
            "auto_save_enabled": graph_service.auto_save_enabled,
            "data_directory": str(graph_service.data_dir),
        }

        if graph_service.sg:
            status["statistics"] = graph_service.get_stats()

        return status
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/database/{file_name}", response_model=dict)
async def delete_database(file_name: str):
    """
    删除数据库文件

    Args:
        file_name: 要删除的数据库文件名

    Returns:
        删除结果
    """
    try:
        result = await graph_service.delete_database(file_name)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/database/rename", response_model=dict)
async def rename_database(request: DatabaseRenameRequest):
    """
    重命名数据库文件

    Args:
        old_name: 旧文件名
        new_name: 新文件名

    Returns:
        重命名结果
    """
    try:
        result = await graph_service.rename_database(request.old_name, request.new_name)
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
