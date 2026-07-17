import { Agent } from "@mastra/core/agent";
import { openai } from "@ai-sdk/openai";
import { brsExtractionPrompt } from "../prompts/brsExtractionPrompt.js";

export const brsExtractionAgent = new Agent({
  id: "brsExtractionAgent",
  name: "brsExtractionAgent",
  instructions: brsExtractionPrompt,
  model: openai("gpt-4o"),
});
