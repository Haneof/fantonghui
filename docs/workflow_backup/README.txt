此目录为 CI workflow 备份，因 GitHub App 无 workflows 权限无法直接推送 .github/workflows/ci.yml

已备份两个文件：
- docs/workflow_backup/ci.yml.txt
- CI_WORKFLOW.yml.bak.txt (根目录)

两者内容均为 .github/workflows/ci.yml 的原文

恢复方法（任选其一）：
1. 在 GitHub 网页端，进入 arena/01a09bc6-fantonghui 分支，新建文件 .github/workflows/ci.yml，粘贴 ci.yml.txt 内容
2. 或在本地有 workflows 权限的环境执行：mkdir -p .github/workflows && cp docs/workflow_backup/ci.yml.txt .github/workflows/ci.yml && git push

