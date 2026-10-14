// The console's own paste schema. Run from repos/contacto-console/apps/web:
//   bun run "../../../../V29-Hunter-Example/validate_console.ts" "../../../../V29-Hunter-Example/v29-hunter-example-flow.json"
import { reactFlowContentSchema } from '../repos/contacto-console/apps/web/src/v2/pages/flow/schemas/react-flow-schemas'

const flow = await Bun.file(process.argv[2]).json()
const result = reactFlowContentSchema.safeParse(flow)
console.log(result.success ? 'console schema: OK' : JSON.stringify(result.error.issues.slice(0, 10), null, 1))
process.exit(result.success ? 0 : 1)
