import { Agent } from "@mastra/core/agent";
import { openai } from "@ai-sdk/openai";
import { usSaDirectVisionPrompt } from "../prompts/usSaDirectVisionPrompt.js";

export const usSaDirectVisionAgent = new Agent({
  id: "usSaDirectVisionAgent",
  name: "usSaDirectVisionAgent",
  instructions: usSaDirectVisionPrompt,
  model: openai("gpt-4o"),
});
