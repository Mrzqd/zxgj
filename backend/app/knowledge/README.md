# 装修知识库

本目录存放应用内置的装修知识库文件。文件内容为项目归纳整理的注意事项和验收清单，用于本地检索和用户下载。

这些资料不是法律意见，也不是对国家/行业标准原文的复制。涉及结构安全、燃气、消防、防水争议、合同纠纷等高风险事项时，应以当地法规、物业要求、设计师/监理/专业机构意见为准。

## 目录说明

- `documents/`：应用启动和 RAG 检索读取的 Markdown 知识库。
- `standards-manifest.json`：国家标准原文导入清单，维护标准标题、官方审查 URL、本地文件路径和输出 Markdown 文件名。
- `raw/`：原始 PDF/Word 标准文件存放目录。该目录用于本地导入，建议不要提交大文件或受版权限制的原文。

## 标准清单范围

`standards-manifest.json` 按装修问答优先级维护标准索引，当前覆盖施工验收、水电、防水、通风空调、消防电气、室内环境、材料环保、施工噪声和建筑垃圾等方向。

- `priority=1`：高频装修问答优先导入，例如住宅装饰装修、装饰装修验收、防水、水电、室内环境、核心材料环保。
- `priority=2`：增强覆盖，例如通用规范、设计标准、通风空调、门窗、地板、胶粘剂等。
- `priority=3`：低频或可能存在替代关系的补充标准，导入前建议先核验现行状态。

常用分类：`core_acceptance`、`water_electricity`、`waterproof`、`installation`、`fire_electrical`、`design`、`environment`、`material`、`construction_environment`。

## 用 MinerU 导入标准原文

1. 在 `.env` 配置 MinerU：

```text
MINERU_API_TOKEN=你的 MinerU API Token
MINERU_MODEL_VERSION=pipeline
```

2. 将合法获取的标准原文放到 manifest 指定路径，例如：

```text
backend/app/knowledge/raw/GB-50327-2001.pdf
backend/app/knowledge/raw/GB-50210-2018.pdf
```

`source_url` 用于审查来源，默认指向全国标准信息公共服务平台或生态环境部搜索入口，不会被脚本当作原文下载地址。若你拿到合法、稳定、可直接下载的原文地址，可以在对应条目配置 `download_url`，脚本才会自动下载到 `raw/`。

3. 解析为 Markdown：

```bash
cd backend
python -m app.scripts.import_standard_documents --ids GB-50327-2001
```

查看可导入标准清单：

```bash
cd backend
python -m app.scripts.import_standard_documents --list
```

按优先级或分类批量导入：

```bash
cd backend
python -m app.scripts.import_standard_documents --max-priority 1 --index
python -m app.scripts.import_standard_documents --categories waterproof water_electricity --index
```

4. 解析并立即向量化内置知识库：

```bash
cd backend
python -m app.scripts.import_standard_documents --ids GB-50327-2001 --index
```

如果使用 Docker Compose：

```bash
docker compose exec backend python -m app.scripts.import_standard_documents --ids GB-50327-2001 --index
docker compose exec backend python -m app.scripts.import_standard_documents --max-priority 1 --index
```
