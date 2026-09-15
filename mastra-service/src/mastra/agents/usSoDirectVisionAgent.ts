import { Agent } from "@mastra/core/agent";
import { openai } from "@ai-sdk/openai";
import { usSoDirectVisionPrompt } from "../prompts/usSoDirectVisionPrompt.js";

export const usSoDirectVisionAgent = new Agent({
  id: "usSoDirectVisionAgent",
  name: "usSoDirectVisionAgent",
  instructions: usSoDirectVisionPrompt,
  model: openai("gpt-4o"),
});
