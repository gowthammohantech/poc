import { Agent } from "@mastra/core/agent";
import { openai } from "@ai-sdk/openai";
import { directVisionPrompt } from "../prompts/directVisionPrompt.js";

export const directVisionInvoiceAgent = new Agent({
  id: "directVisionInvoiceAgent",
  name: "directVisionInvoiceAgent",
  instructions: directVisionPrompt,
  model: openai("gpt-4o"),
});
