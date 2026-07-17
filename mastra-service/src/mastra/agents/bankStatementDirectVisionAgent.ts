import { Agent } from "@mastra/core/agent";
import { openai } from "@ai-sdk/openai";
import { bankStatementDirectVisionPrompt } from "../prompts/bankStatementDirectVisionPrompt.js";

export const bankStatementDirectVisionAgent = new Agent({
  id: "bankStatementDirectVisionAgent",
  name: "bankStatementDirectVisionAgent",
  instructions: bankStatementDirectVisionPrompt,
  model: openai("gpt-4o"),
});
