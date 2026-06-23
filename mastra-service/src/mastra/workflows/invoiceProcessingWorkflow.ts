import { createWorkflow, createStep } from "@mastra/core/workflows";
import { z } from "zod";
import { invoiceOcrRouterAgent } from "../agents/invoiceOcrRouterAgent.js";
import { invoiceExtractionAgent } from "../agents/invoiceExtractionAgent.js";
import { directVisionInvoiceAgent } from "../agents/directVisionInvoiceAgent.js";
import { invoiceValidationAgent } from "../agents/invoiceValidationAgent.js";

const routeStep = createStep({
  id: "route",
  inputSchema: z.object({
    document_id: z.string(),
    complexity_score: z.number(),
    complexity_level: z.string(),
    reasons: z.array(z.string()),
    page_count: z.number(),
    must_use_llm: z.boolean(),
    expected_fields: z.string().optional(),
  }),
  outputSchema: z.object({
    engine: z.string(),
    reason: z.string(),
    document_id: z.string(),
    complexity_score: z.number(),
    must_use_llm: z.boolean(),
    expected_fields: z.string().optional(),
  }),
  execute: async ({ inputData }) => {
    const prompt = `Route this invoice. complexity_score: ${inputData.complexity_score}, must_use_llm: ${inputData.must_use_llm}. Return JSON {engine, reason}.`;
    const result = await invoiceOcrRouterAgent.generate([
      { role: "user", content: prompt },
    ]);
    let parsed = { engine: "TESSERACT", reason: "default" };
    try {
      const text = result.text || "";
      const match = text.match(/\{[\s\S]*\}/);
      if (match) parsed = JSON.parse(match[0]);
    } catch {}
    return {
      engine: parsed.engine || "TESSERACT",
      reason: parsed.reason || "",
      document_id: inputData.document_id,
      complexity_score: inputData.complexity_score,
      must_use_llm: inputData.must_use_llm,
      expected_fields: inputData.expected_fields,
    };
  },
});

const validateStep = createStep({
  id: "validate",
  inputSchema: z.object({
    document_id: z.string(),
    invoice_json: z.record(z.unknown()),
  }),
  outputSchema: z.object({
    llm_checks: z.array(z.record(z.unknown())),
    warnings: z.array(z.string()),
  }),
  execute: async ({ inputData }) => {
    const prompt = `Validate this invoice JSON:\n${JSON.stringify(inputData.invoice_json, null, 2)}\nReturn JSON {llm_checks, warnings}.`;
    const result = await invoiceValidationAgent.generate([
      { role: "user", content: prompt },
    ]);
    let parsed = { llm_checks: [], warnings: [] };
    try {
      const text = result.text || "";
      const match = text.match(/\{[\s\S]*\}/);
      if (match) parsed = JSON.parse(match[0]);
    } catch {}
    return {
      llm_checks: parsed.llm_checks || [],
      warnings: parsed.warnings || [],
    };
  },
});

export const invoiceProcessingWorkflow = createWorkflow({
  id: "invoiceProcessingWorkflow",
  inputSchema: z.object({
    document_id: z.string(),
    complexity_score: z.number(),
    complexity_level: z.string(),
    reasons: z.array(z.string()),
    page_count: z.number(),
    must_use_llm: z.boolean(),
    expected_fields: z.string().optional(),
  }),
  outputSchema: z.object({
    engine: z.string(),
    reason: z.string(),
  }),
})
  .then(routeStep)
  .commit();
