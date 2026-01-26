#!/bin/bash
# Type Generation Script
# Generates TypeScript and Python types from JSON schemas

set -e

echo "🔄 Generating types from JSON schemas..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SCHEMAS_DIR="$PROJECT_ROOT/shared/schemas"
TYPES_DIR="$PROJECT_ROOT/shared/types"

# Create types directory if it doesn't exist
mkdir -p "$TYPES_DIR"

# Generate TypeScript types using quicktype
echo "📝 Generating TypeScript types..."
npx quicktype \
  --src "$SCHEMAS_DIR/email.schema.json" \
  --src "$SCHEMAS_DIR/thread.schema.json" \
  --src "$SCHEMAS_DIR/analysis.schema.json" \
  --src-lang schema \
  --lang typescript \
  --out "$TYPES_DIR/index.ts" \
  --just-types \
  --prefer-unions \
  --nice-property-names

# Generate Python types using datamodel-code-generator
echo "🐍 Generating Python types..."
pip install -q datamodel-code-generator

datamodel-codegen \
  --input "$SCHEMAS_DIR/email.schema.json" \
  --input "$SCHEMAS_DIR/thread.schema.json" \
  --input "$SCHEMAS_DIR/analysis.schema.json" \
  --input-file-type jsonschema \
  --output "$TYPES_DIR/models.py" \
  --use-standard-collections \
  --use-schema-description \
  --field-constraints

echo "✅ Type generation complete!"
echo "   TypeScript: $TYPES_DIR/index.ts"
echo "   Python: $TYPES_DIR/models.py"
