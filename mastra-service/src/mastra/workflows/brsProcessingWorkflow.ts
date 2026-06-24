import { createWorkflow, createStep } from "@mastra/core/workflows";
import { z } from "zod";
import { brsValidationAgent } from "../agents/brsValidationAgent.js";

const brsValidateStep = createStep({
  id: "brs_validate",
  inputSchema: z.object({
    document_id: z.string(),
    brs_json: z.record(z.unknown()),
  }),
  outputSchema: z.object({
    llm_checks: z.array(z.record(z.unknown())),
    warnings: z.array(z.string()),
  }),
  execute: async ({ inputData }) => {
    const prompt = `Validate this BRS JSON:\n${JSON.stringify(inputData.brs_json, null, 2)}\nReturn JSON {llm_checks, warnings, confidence_adjustments}.`;
    const result = await brsValidationAgent.generate([
      { role: "user", content: prompt },
    ]);
    let parsed: { llm_checks: unknown[]; warnings: string[] } = {
      llm_checks: [],
      warnings: [],
    };
    try {
      const text = result.text || "";
      const match = text.match(/\{[\s\S]*\}/);
      if (match) parsed = JSON.parse(match[0]);
    } catch {}
    return {
      llm_checks: (parsed.llm_checks || []) as Record<string, unknown>[],
      warnings: parsed.warnings || [],
    };
  },
});

export const brsProcessingWorkflow = createWorkflow({
  id: "brsProcessingWorkflow",
  inputSchema: z.object({
    document_id: z.string(),
    brs_json: z.record(z.unknown()),
  }),
  outputSchema: z.object({
    llm_checks: z.array(z.record(z.unknown())),
    warnings: z.array(z.string()),
  }),
})
  .then(brsValidateStep)
  .commit();
