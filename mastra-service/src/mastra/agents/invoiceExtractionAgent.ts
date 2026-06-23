import { Agent } from "@mastra/core/agent";
import { openai } from "@ai-sdk/openai";
import { extractionPrompt } from "../prompts/extractionPrompt.js";

export const invoiceExtractionAgent = new Agent({
  id: "invoiceExtractionAgent",
  name: "invoiceExtractionAgent",
  instructions: extractionPrompt,
  model: openai("gpt-4o"),
});
