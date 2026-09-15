import { Mastra } from "@mastra/core/mastra";
import { invoiceOcrRouterAgent } from "./agents/invoiceOcrRouterAgent.js";
import { invoiceExtractionAgent } from "./agents/invoiceExtractionAgent.js";
import { directVisionInvoiceAgent } from "./agents/directVisionInvoiceAgent.js";
import { invoiceValidationAgent } from "./agents/invoiceValidationAgent.js";
import { invoiceProcessingWorkflow } from "./workflows/invoiceProcessingWorkflow.js";
import { brsDirectVisionAgent } from "./agents/brsDirectVisionAgent.js";
import { brsExtractionAgent } from "./agents/brsExtractionAgent.js";
import { brsValidationAgent } from "./agents/brsValidationAgent.js";
import { bankStatementDirectVisionAgent } from "./agents/bankStatementDirectVisionAgent.js";
import { brsProcessingWorkflow } from "./workflows/brsProcessingWorkflow.js";
import { usDocClassifierAgent } from "./agents/usDocClassifierAgent.js";
import { usSaDirectVisionAgent } from "./agents/usSaDirectVisionAgent.js";
import { usSoDirectVisionAgent } from "./agents/usSoDirectVisionAgent.js";
import { usValidationAgent } from "./agents/usValidationAgent.js";

export const mastra = new Mastra({
  agents: {
    invoiceOcrRouterAgent,
    invoiceExtractionAgent,
    directVisionInvoiceAgent,
    invoiceValidationAgent,
    brsDirectVisionAgent,
    brsExtractionAgent,
    brsValidationAgent,
    bankStatementDirectVisionAgent,
    usDocClassifierAgent,
    usSaDirectVisionAgent,
    usSoDirectVisionAgent,
    usValidationAgent,
  },
  workflows: {
    invoiceProcessingWorkflow,
    brsProcessingWorkflow,
  },
});
