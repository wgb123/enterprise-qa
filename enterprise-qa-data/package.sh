#!/bin/bash
# 企业智能问答助手 - 试题包打包脚本
# 生成 candidate-package.zip 供候选人使用

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PACKAGE_NAME="enterprise-qa-data.zip"
DEST_DIR="$SCRIPT_DIR/../../dist/interview-exam/"

echo "=========================================="
echo "  企业智能问答助手 - 试题包打包"
echo "=========================================="

# 创建目标目录
mkdir -p "$DEST_DIR"

# 清理旧包
rm -f "$DEST_DIR/$PACKAGE_NAME"
rm -f enterprise.db

echo "✓ 清理完成..."

# 验证文件结构
echo ""
echo "=========================================="
echo "  文件结构"
echo "=========================================="
find . -type f ! -name "*.zip" ! -name "package.sh" | sort

# 打包（排除 zip 文件和脚本本身）
echo ""
echo "=========================================="
echo "  打包中..."
echo "=========================================="

zip -r "$DEST_DIR/$PACKAGE_NAME" \
    README.md \
    schema.sql \
    seed_data.sql \
    init_db.sh \
    config.yaml.example \
    knowledge/

echo ""
echo "✓ 打包完成：$DEST_DIR/$PACKAGE_NAME"

# 验证包内容
echo ""
echo "=========================================="
echo "  包内容验证"
echo "=========================================="
unzip -l "$DEST_DIR/$PACKAGE_NAME"

# 解压测试
echo ""
echo "=========================================="
echo "  解压测试"
echo "=========================================="
rm -rf /tmp/enterprise-qa-test
mkdir -p /tmp/enterprise-qa-test
cd /tmp/enterprise-qa-test
unzip -o "$DEST_DIR/$PACKAGE_NAME" > /dev/null
chmod +x init_db.sh
./init_db.sh

echo ""
echo "=========================================="
echo "  ✓ 所有一致性检查通过"
echo "=========================================="

# 清理
rm -rf /tmp/enterprise-qa-test
cd "$SCRIPT_DIR"

echo ""
echo "试题包位置：$DEST_DIR/$PACKAGE_NAME"
echo "=========================================="
