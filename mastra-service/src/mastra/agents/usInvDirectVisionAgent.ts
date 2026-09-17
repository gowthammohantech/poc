import { Agent } from "@mastra/core/agent";
import { openai } from "@ai-sdk/openai";
import { usInvDirectVisionPrompt } from "../prompts/usInvDirectVisionPrompt.js";

export const usInvDirectVisionAgent = new Agent({
  id: "usInvDirectVisionAgent",
  name: "usInvDirectVisionAgent",
  instructions: usInvDirectVisionPrompt,
  model: openai("gpt-4o"),
});
