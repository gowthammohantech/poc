import { Agent } from "@mastra/core/agent";
import { openai } from "@ai-sdk/openai";
import { validationPrompt } from "../prompts/validationPrompt.js";

export const invoiceValidationAgent = new Agent({
  id: "invoiceValidationAgent",
  name: "invoiceValidationAgent",
  instructions: validationPrompt,
  model: openai("gpt-4o-mini"),
});
