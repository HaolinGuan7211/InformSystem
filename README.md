# InformSystem

校园通知筛选系统的初始工程骨架已经按模块化方式建立，当前完成了模块 1 `Ingestion Module` 的第一版实现。

## 当前结构

```text
backend/
  app/
    api/
    core/
    services/
      ingestion/
docs/
  modules/
mocks/
  ingestion/
scripts/
```

## 本地运行

```bash
pip install -e .[dev]
uvicorn backend.app.main:app --reload
```

服务启动后可用：

- `POST /api/v1/webhooks/{source_id}`
- `POST /api/v1/ingestion/manual`
- `POST /api/v1/ingestion/replay/{event_id}`

## 本地 demo

```bash
python scripts/demo_ingestion.py
```

## 测试

```bash
pytest
```

