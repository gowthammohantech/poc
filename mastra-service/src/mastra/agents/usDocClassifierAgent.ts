import { Agent } from "@mastra/core/agent";
import { openai } from "@ai-sdk/openai";
import { usDocClassifierPrompt } from "../prompts/usDocClassifierPrompt.js";

export const usDocClassifierAgent = new Agent({
  id: "usDocClassifierAgent",
  name: "usDocClassifierAgent",
  instructions: usDocClassifierPrompt,
  model: openai("gpt-4o-mini"),
});
