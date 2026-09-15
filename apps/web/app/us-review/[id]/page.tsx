"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useForm, useFieldArray } from "react-hook-form";

import ConfidenceBadge from "@/components/ConfidenceBadge";
import PagePreview from "@/components/PagePreview";
import { Field, NavArrow, inputCls, tdInputCls } from "@/components/review/ReviewPrimitives";
import SaScheduleGrid from "@/components/review/SaScheduleGrid";
import SoLineItems from "@/components/review/SoLineItems";
import { SkeletonBar } from "@/components/Skeleton";
import { getDocuments, getExportUrl, getUsReview, submitUsReview } from "@/lib/api";
import { normalizeCountry } from "@/lib/country";
import type { Document } from "@/types/invoice";
import type { UsDocumentData, UsReviewData, UsSaData, UsSoData } from "@/types/usDocument";

export default function UsReviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const search = useSearchParams();
  const sourceFilter = search.get("source");
  const countryFilter = search.get("country");

  const [review, setReview] = useState<UsReviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [submitMsg, setSubmitMsg] = useState("");
  const [prevId, setPrevId] = useState<string | null>(null);
  const [nextId, setNextId] = useState<string | null>(null);

  const { register, control, handleSubmit, reset } = useForm<UsDocumentData>();

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setSubmitMsg("");
    getUsReview(id as string)
      .then((data) => {
        // An India invoice reaching this route has a different shape entirely.
        // Redirecting on the document's own country, not the selector, means a
        // bookmark or a stale link still lands on the right form.
        if (normalizeCountry(data.country) !== "USA") {
          router.replace(`/review/${id}${window.location.search}`);
          return;
        }
        setReview(data);
        reset(data.invoice);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [id, reset, router]);

  // Sibling documents, in the order the list shows them, so the arrows walk
  // the list the user came from -- and stay inside one country, or the arrows
  // would jump between two entirely different review screens.
  useEffect(() => {
    getDocuments()
      .then((data: Document[]) => {
        const siblings = data.filter(
          (d) =>
            (!sourceFilter || (d.source ?? "MANUAL") === sourceFilter) &&
            (!countryFilter || normalizeCountry(d.country) === normalizeCountry(countryFilter)),
        );
        const index = siblings.findIndex((d) => d.id === id);
        setPrevId(index > 0 ? siblings[index - 1].id : null);
        setNextId(index >= 0 && index < siblings.length - 1 ? siblings[index + 1].id : null);
      })
      .catch(() => {});
  }, [id, sourceFilter, countryFilter]);

  const go = useCallback(
    (target: string | null) => {
      if (target) router.push(`/us-review/${target}${window.location.search}`);
    },
    [router],
  );

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "ArrowLeft") go(prevId);
      if (e.key === "ArrowRight") go(nextId);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, prevId, nextId]);

  async function onSubmit(formData: UsDocumentData) {
    setSubmitting(true);
    setSubmitMsg("");
    try {
      await submitUsReview(id as string, formData);
      setSubmitMsg("Submitted successfully.");
      setReview((prev) => (prev ? { ...prev, status: "COMPLETED" } : prev));
    } catch {
      setSubmitMsg("Submit failed. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) return <ReviewSkeleton />;
  if (!review) {
    return (
      <div className="p-8 text-center text-gray-500">
        Document not found.
      </div>
    );
  }

  const doc = review.invoice;
  const isSa = doc?.document_type === "SA";
  const val = review.validation;
  const conf = review.confidence ?? {};
  const docStatus = review.status || val?.status;
  const typeLabel =
    review.doc_type === "SA"
      ? "Shipping Authorization"
      : review.doc_type === "SO"
        ? "Purchase Order"
        : "Unclassified";

  return (
    <div className="bg-gray-50 min-h-screen">
      <NavArrow side="left" disabled={!prevId} onClick={() => go(prevId)} label="Previous document" />
      <NavArrow side="right" disabled={!nextId} onClick={() => go(nextId)} label="Next document" />

      <header className="bg-white border-b px-6 py-3 flex items-center gap-3 flex-wrap">
        <div>
          <h1 className="text-lg font-semibold text-gray-900">US Document Review</h1>
          <p className="text-xs text-gray-500 font-mono">{review.document_id}</p>
        </div>

        <span
          className={`px-3 py-1 rounded-full border text-sm font-medium ${
            review.doc_type === "UNKNOWN" || !review.doc_type
              ? "bg-amber-50 text-amber-700 border-amber-200"
              : "bg-violet-50 text-violet-700 border-violet-200"
          }`}
        >
          {typeLabel}
        </span>

        <span
          className={`px-3 py-1 rounded-full border text-sm font-medium ${
            docStatus === "VALID" || docStatus === "COMPLETED"
              ? "bg-green-50 text-green-700 border-green-200"
              : docStatus === "INVALID"
                ? "bg-red-50 text-red-700 border-red-200"
                : "bg-yellow-50 text-yellow-700 border-yellow-200"
          }`}
        >
          {docStatus}
        </span>

        {review.ocr_engine && (
          <span className="px-3 py-1 rounded-full border border-gray-200 bg-gray-50 text-sm text-gray-600 font-mono">
            {review.ocr_engine}
          </span>
        )}

        <details className="relative ml-auto">
          <summary className="list-none cursor-pointer text-sm bg-gray-100 text-gray-700 hover:bg-gray-200 px-3 py-1.5 rounded-lg transition-colors">
            Export
          </summary>
          <div className="absolute right-0 top-full z-10 mt-1 w-32 overflow-hidden rounded-lg border border-gray-200 bg-white py-1 shadow-lg">
            {(["json", "csv", "excel"] as const).map((format) => (
              <a
                key={format}
                href={getExportUrl(review.document_id, format)}
                className="block px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
              >
                {format.toUpperCase()}
              </a>
            ))}
          </div>
        </details>
      </header>

      {review.doc_type === "UNKNOWN" && (
        <div className="bg-amber-50 border-b border-amber-200 px-6 py-2 text-sm text-amber-800">
          This document could not be classified, so it was read as a purchase order. Correct any
          fields below, or re-upload it if it is a shipping authorization.
        </div>
      )}

      {val?.errors?.length > 0 && (
        <div className="bg-red-50 border-b border-red-200 px-6 py-2">
          {val.errors.map((e, i) => (
            <p key={i} className="text-sm text-red-700">• {e}</p>
          ))}
        </div>
      )}
      {val?.warnings?.length > 0 && (
        <div className="bg-yellow-50 border-b border-yellow-200 px-6 py-2">
          {val.warnings.map((w, i) => (
            <p key={i} className="text-sm text-yellow-700">• {w}</p>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-0 h-[calc(100vh-120px)]">
        <div className="border-r overflow-y-auto">
          <PagePreview pageUrls={review.page_urls} ocrReference={review.ocr_reference} />
        </div>

        <form onSubmit={handleSubmit(onSubmit)} className="overflow-y-auto p-4 space-y-6">
          {isSa ? (
            <SaSections
              doc={doc as UsSaData}
              control={control}
              register={register}
              confidence={conf}
            />
          ) : (
            <SoSections
              doc={doc as UsSoData}
              control={control}
              register={register}
              confidence={conf}
            />
          )}

          {val?.rule_checks?.length > 0 && (
            <section className="bg-white rounded-lg border p-4 space-y-2">
              <h2 className="text-xs font-semibold uppercase text-gray-500">Validation Checks</h2>
              {val.rule_checks.map((check, i) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <span className={check.passed ? "text-green-600" : "text-red-600"}>
                    {check.passed ? "✓" : "✗"}
                  </span>
                  <span className={check.passed ? "text-gray-600" : "text-red-700"}>
                    {check.message}
                  </span>
                </div>
              ))}
            </section>
          )}

          {submitMsg && (
            <p
              className={`text-sm ${
                submitMsg.startsWith("Submitted") ? "text-green-600" : "text-red-600"
              }`}
            >
              {submitMsg}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 text-white font-medium py-2.5 rounded-lg transition-colors"
          >
            {submitting ? "Submitting..." : "Submit Corrected Document"}
          </button>
        </form>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------------ */

type SectionProps<T> = {
  doc: T;
  // react-hook-form's generics do not narrow across a union, so these are
  // passed through untyped rather than fighting the inference at every field.
  /* eslint-disable @typescript-eslint/no-explicit-any */
  control: any;
  register: any;
  /* eslint-enable @typescript-eslint/no-explicit-any */
  confidence: Record<string, number>;
};

function SaSections({ doc, control, register, confidence }: SectionProps<UsSaData>) {
  const { fields: noteFields } = useFieldArray({ control, name: "terms_notes" as never });

  return (
    <>
      <section className="bg-white rounded-lg border p-4 space-y-3">
        <h2 className="text-xs font-semibold uppercase text-gray-500 flex items-center gap-2">
          Release
          <ConfidenceBadge value={confidence.document_number ?? confidence.overall ?? 0} />
        </h2>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Release Number">
            <input className={inputCls} {...register("release_number")} />
          </Field>
          <Field label="Release Date">
            <input className={inputCls} {...register("release_date")} />
          </Field>
          <Field label="Received By">
            <input className={inputCls} {...register("received_by")} />
          </Field>
          <Field label="Received At">
            <input className={inputCls} {...register("received_at")} />
          </Field>
        </div>
      </section>

      <section className="bg-white rounded-lg border p-4 space-y-3">
        <h2 className="text-xs font-semibold uppercase text-gray-500 flex items-center gap-2">
          Issuer
          <ConfidenceBadge value={confidence.parties ?? confidence.overall ?? 0} />
        </h2>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Name">
            <input className={inputCls} {...register("issuer.name")} />
          </Field>
          <Field label="Phone">
            <input className={inputCls} {...register("issuer.phone")} />
          </Field>
          <Field label="Contact">
            <input className={inputCls} {...register("issuer.contact")} />
          </Field>
          <Field label="Address" colSpan>
            <textarea rows={2} className={inputCls} {...register("issuer.address")} />
          </Field>
        </div>
      </section>

      <section className="bg-white rounded-lg border p-4 space-y-3">
        <h2 className="text-xs font-semibold uppercase text-gray-500">Supplier</h2>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Name">
            <input className={inputCls} {...register("supplier.name")} />
          </Field>
          <Field label="Supplier Code">
            <input className={inputCls} {...register("supplier.code")} />
          </Field>
          <Field label="Contact" colSpan>
            <input className={inputCls} {...register("supplier.contact")} />
          </Field>
        </div>
      </section>

      <SaScheduleGrid doc={doc} control={control} register={register} confidence={confidence} />

      {noteFields.length > 0 && (
        <section className="bg-white rounded-lg border p-4 space-y-2">
          <h2 className="text-xs font-semibold uppercase text-gray-500">Terms &amp; Notes</h2>
          {noteFields.map((field, i) => (
            <textarea
              key={field.id}
              rows={2}
              className={inputCls}
              {...register(`terms_notes.${i}` as const)}
            />
          ))}
        </section>
      )}
    </>
  );
}

function SoSections({ doc, control, register, confidence }: SectionProps<UsSoData>) {
  return (
    <>
      <section className="bg-white rounded-lg border p-4 space-y-3">
        <h2 className="text-xs font-semibold uppercase text-gray-500 flex items-center gap-2">
          Order
          <ConfidenceBadge value={confidence.document_number ?? confidence.overall ?? 0} />
        </h2>
        <div className="grid grid-cols-2 gap-3">
          <Field label="PO Number">
            <input className={inputCls} {...register("order_number")} />
          </Field>
          <Field label="Order Date">
            <input className={inputCls} {...register("order_date")} />
          </Field>
          <Field label="Currency">
            <input className={inputCls} placeholder="USD" {...register("currency")} />
          </Field>
          <Field label="Payment Terms">
            <input className={inputCls} {...register("payment_terms")} />
          </Field>
          <Field label="Freight Terms">
            <input className={inputCls} {...register("freight_terms")} />
          </Field>
          <Field label="Ship Via">
            <input className={inputCls} {...register("ship_via")} />
          </Field>
          <Field label="Received By">
            <input className={inputCls} {...register("received_by")} />
          </Field>
          <Field label="Received At">
            <input className={inputCls} {...register("received_at")} />
          </Field>
        </div>
      </section>

      {(
        [
          ["vendor", "Vendor", true],
          ["buyer", "Buyer", false],
          ["bill_to", "Bill To", false],
          ["ship_to", "Ship To", false],
        ] as const
      ).map(([key, label, withCode]) => (
        <section key={key} className="bg-white rounded-lg border p-4 space-y-3">
          <h2 className="text-xs font-semibold uppercase text-gray-500 flex items-center gap-2">
            {label}
            {key === "vendor" && (
              <ConfidenceBadge value={confidence.parties ?? confidence.overall ?? 0} />
            )}
          </h2>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Name">
              <input className={inputCls} {...register(`${key}.name`)} />
            </Field>
            {withCode ? (
              <Field label="Vendor Code">
                <input className={inputCls} {...register(`${key}.code`)} />
              </Field>
            ) : (
              <Field label="Phone">
                <input className={inputCls} {...register(`${key}.phone`)} />
              </Field>
            )}
            <Field label="Contact">
              <input className={inputCls} {...register(`${key}.contact`)} />
            </Field>
            {withCode && (
              <Field label="Phone">
                <input className={inputCls} {...register(`${key}.phone`)} />
              </Field>
            )}
            <Field label="Address" colSpan>
              <textarea rows={2} className={inputCls} {...register(`${key}.address`)} />
            </Field>
          </div>
        </section>
      ))}

      <SoLineItems doc={doc} control={control} register={register} confidence={confidence} />

      <section className="bg-white rounded-lg border p-4 space-y-3">
        <h2 className="text-xs font-semibold uppercase text-gray-500">Totals</h2>
        <p className="text-xs text-gray-400">
          Many US purchase orders print no totals block. Blank here means the document carried
          none, not that a figure was missed.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {(
            ["subtotal", "sales_tax", "freight", "discount", "grand_total"] as const
          ).map((key) => (
            <Field
              key={key}
              label={key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
            >
              <input
                type="number"
                step="any"
                className={inputCls}
                {...register(`totals.${key}`, { valueAsNumber: true })}
              />
            </Field>
          ))}
        </div>
      </section>
    </>
  );
}

function ReviewSkeleton() {
  return (
    <div className="bg-gray-50 min-h-screen">
      <div className="bg-white border-b px-6 py-3 flex items-center gap-3">
        <SkeletonBar className="h-5 w-48" />
        <SkeletonBar className="h-6 w-32 rounded-full" />
        <SkeletonBar className="h-6 w-24 rounded-full" />
      </div>
      <div className="grid grid-cols-2 gap-0 h-[calc(100vh-120px)]">
        <div className="border-r p-4">
          <SkeletonBar className="h-full w-full" />
        </div>
        <div className="p-4 space-y-4">
          {[0, 1, 2].map((i) => (
            <section key={i} className="bg-white rounded-lg border p-4 space-y-3">
              <SkeletonBar className="h-3 w-24" />
              <div className="grid grid-cols-2 gap-3">
                {[0, 1, 2, 3].map((j) => (
                  <SkeletonBar key={j} className="h-8 w-full" />
                ))}
              </div>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
