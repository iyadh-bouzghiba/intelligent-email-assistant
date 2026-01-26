# Shared Types and Schemas

This directory contains the **single source of truth** for data structures used across the Email Assistant application.

## Structure

```
shared/
├── schemas/          # JSON Schema definitions
│   ├── email.schema.json
│   ├── thread.schema.json
│   └── analysis.schema.json
└── types/            # Generated types (DO NOT EDIT MANUALLY)
    ├── index.ts      # TypeScript types
    └── models.py     # Python Pydantic models
```

## Usage

### Generating Types

After modifying any schema, regenerate types:

**Linux/Mac**:
```bash
./scripts/generate-types.sh
```

**Windows**:
```powershell
.\scripts\generate-types.ps1
```

### Backend (Python)

```python
from shared.types.models import StandardEmail, ThreadAnalysis

email = StandardEmail(
    id="123",
    sender="John Doe <john@example.com>",
    subject="Test",
    body_text="Hello",
    timestamp=datetime.now(),
    thread_id="thread_1"
)
```

### Frontend (TypeScript)

```typescript
import { StandardEmail, ThreadAnalysis } from '@shared/types';

const email: StandardEmail = {
  id: "123",
  sender: "John Doe <john@example.com>",
  subject: "Test",
  body_text: "Hello",
  timestamp: new Date().toISOString(),
  thread_id: "thread_1",
  recipients: []
};
```

## Benefits

- ✅ **Type Safety**: Frontend and backend use identical types
- ✅ **Single Source of Truth**: Schemas define the contract
- ✅ **Auto-Generated**: No manual type duplication
- ✅ **Validation**: JSON Schema enables runtime validation
- ✅ **Documentation**: Schemas serve as API documentation

## Workflow

1. Modify schema in `schemas/`
2. Run `generate-types` script
3. Commit both schema and generated types
4. Types are automatically in sync across frontend/backend
