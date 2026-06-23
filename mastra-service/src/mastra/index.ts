import { Mastra } from "@mastra/core/mastra";
import { invoiceOcrRouterAgent } from "./agents/invoiceOcrRouterAgent.js";
import { invoiceExtractionAgent } from "./agents/invoiceExtractionAgent.js";
import { directVisionInvoiceAgent } from "./agents/directVisionInvoiceAgent.js";
import { invoiceValidationAgent } from "./agents/invoiceValidationAgent.js";
import { invoiceProcessingWorkflow } from "./workflows/invoiceProcessingWorkflow.js";

export const mastra = new Mastra({
  agents: {
    invoiceOcrRouterAgent,
    invoiceExtractionAgent,
    directVisionInvoiceAgent,
    invoiceValidationAgent,
  },
  workflows: {
    invoiceProcessingWorkflow,
  },
});
