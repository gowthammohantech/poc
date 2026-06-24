import { Agent } from "@mastra/core/agent";
import { openai } from "@ai-sdk/openai";
import { brsValidationPrompt } from "../prompts/brsValidationPrompt.js";

export const brsValidationAgent = new Agent({
  id: "brsValidationAgent",
  name: "brsValidationAgent",
  instructions: brsValidationPrompt,
  model: openai("gpt-4o-mini"),
});
