import { Agent } from "@mastra/core/agent";
import { openai } from "@ai-sdk/openai";
import { routerPrompt } from "../prompts/routerPrompt.js";

export const invoiceOcrRouterAgent = new Agent({
  id: "invoiceOcrRouterAgent",
  name: "invoiceOcrRouterAgent",
  instructions: routerPrompt,
  model: openai("gpt-4o-mini"),
});
