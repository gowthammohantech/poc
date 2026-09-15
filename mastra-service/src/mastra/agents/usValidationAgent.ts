import { Agent } from "@mastra/core/agent";
import { openai } from "@ai-sdk/openai";
import { usValidationPrompt } from "../prompts/usValidationPrompt.js";

export const usValidationAgent = new Agent({
  id: "usValidationAgent",
  name: "usValidationAgent",
  instructions: usValidationPrompt,
  model: openai("gpt-4o-mini"),
});
