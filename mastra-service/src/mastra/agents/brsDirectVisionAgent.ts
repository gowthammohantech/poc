import { Agent } from "@mastra/core/agent";
import { openai } from "@ai-sdk/openai";
import { brsDirectVisionPrompt } from "../prompts/brsDirectVisionPrompt.js";

export const brsDirectVisionAgent = new Agent({
  id: "brsDirectVisionAgent",
  name: "brsDirectVisionAgent",
  instructions: brsDirectVisionPrompt,
  model: openai("gpt-4o"),
});
