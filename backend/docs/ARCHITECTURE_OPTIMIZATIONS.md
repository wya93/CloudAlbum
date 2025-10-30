# CloudAlbum 架构优化说明

本次改动在不改变现有 API 契约的前提下，围绕上传与元数据处理能力拆分出服务层，提升可维护性与可靠性。

## 关键调整

### 1. 存储集成抽象
- 新增 `gallery.services.storage.S3UploadService` 与 `get_upload_storage_service`，集中封装 S3 直传、分片上传的客户端初始化及调用细节。
- 当未启用 S3 或缺失 `AWS_STORAGE_BUCKET_NAME` 时立即抛出 `StorageBackendNotConfigured`，由视图层转成一致的 400 响应，避免运行期才触发的 `NameError`/配置错误。

### 2. 上传编排服务
- 新增 `gallery.services.uploads`，统一调度缩略图、EXIF、AI 标签与人脸聚类任务，提供 `create_photos_from_form_upload` 复用表单上传流程。
- 视图层职责收敛为参数校验 + 服务编排，上传后置逻辑由服务层维护，减少重复代码与漏调任务的风险。

### 3. 元数据提取服务
- 新增 `gallery.services.metadata.extract_exif_metadata`，集中处理 EXIF 解析、时间/坐标转换与异常容错。
- `extract_exif_task` 只负责调度与落库，修复了原实现中 `Photo.objects.get(id=photo.id)`、`if exit` 等运行期错误，并保证 `update_fields` 正确。

### 4. 视图模块分层
- `gallery/views/` 目录将原有的 `views.py`、`views_auto.py`、`views_search.py`、`views_recommend.py` 拆分为 `base.py`、`auto.py`、`search.py`、`recommend.py`，通过 `__init__.py` 聚合对外入口，便于按子域维护。
- 搜索、自动相册等接口统一挂载 `IsAuthenticated` 权限，并在自动相册接口补充参数校验与所有者过滤，降低越权风险。

## 迁移指南

- 新增的服务模块位于 `gallery/services/`，需要在引用处通过 `from gallery.services import ...` 导入。
- 视图层如需添加新的上传入口，应调用 `dispatch_post_upload_tasks(photo.id)` 以保持异步处理一致性。
- 如需扩展存储后端，推荐以 `S3UploadService` 为模板实现新的服务对象，并在 `get_upload_storage_service` 中添加分支。

## 后续建议

- 将 AI 相关任务中模型加载逻辑迁移至服务层，实现懒加载与缓存。
- 在 `gallery.services.metadata` 中补充单元测试，覆盖多时区与异常 EXIF 案例。
- 基于服务层可以进一步引入领域 use-case 对象，削减视图层对 ORM 的直接依赖。
