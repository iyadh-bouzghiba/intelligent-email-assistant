# Type Generation Script (Windows)
# Generates TypeScript and Python types from JSON schemas

Write-Host "🔄 Generating types from JSON schemas..." -ForegroundColor Cyan

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$SchemasDir = Join-Path $ProjectRoot "shared\schemas"
$TypesDir = Join-Path $ProjectRoot "shared\types"

# Create types directory if it doesn't exist
New-Item -ItemType Directory -Force -Path $TypesDir | Out-Null

# Generate TypeScript types using quicktype
Write-Host "📝 Generating TypeScript types..." -ForegroundColor Yellow
npx quicktype `
  --src "$SchemasDir\email.schema.json" `
  --src "$SchemasDir\thread.schema.json" `
  --src "$SchemasDir\analysis.schema.json" `
  --src-lang schema `
  --lang typescript `
  --out "$TypesDir\index.ts" `
  --just-types `
  --prefer-unions `
  --nice-property-names

# Generate Python types using datamodel-code-generator
Write-Host "🐍 Generating Python types..." -ForegroundColor Yellow
pip install -q datamodel-code-generator

datamodel-codegen `
  --input "$SchemasDir\email.schema.json" `
  --input "$SchemasDir\thread.schema.json" `
  --input "$SchemasDir\analysis.schema.json" `
  --input-file-type jsonschema `
  --output "$TypesDir\models.py" `
  --use-standard-collections `
  --use-schema-description `
  --field-constraints

Write-Host "✅ Type generation complete!" -ForegroundColor Green
Write-Host "   TypeScript: $TypesDir\index.ts"
Write-Host "   Python: $TypesDir\models.py"
