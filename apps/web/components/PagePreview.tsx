"use client";

import { useState } from "react";
import { getPageImageUrl } from "@/lib/api";
import type { OcrReference } from "@/types/invoice";

interface PagePreviewProps {
  pageUrls: string[];
  ocrReference?: OcrReference | null;
}

export default function PagePreview({ pageUrls, ocrReference }: PagePreviewProps) {
  const [current, setCurrent] = useState(0);

  if (!pageUrls || pageUrls.length === 0) {
    return (
      <div className="flex items-center justify-center h-96 bg-gray-100 rounded-lg">
        <p className="text-gray-500">No pages available</p>
      </div>
    );
  }

  const referencePage = ocrReference?.pages[current];
  const hasReferenceBoxes = Boolean(
    referencePage && referencePage.width > 0 && referencePage.height > 0 && referencePage.boxes.length > 0
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="relative bg-gray-100 rounded-lg overflow-hidden" style={{ minHeight: "500px" }}>
        <div className="relative inline-block max-w-full">
          <img
            src={getPageImageUrl(pageUrls[current])}
            alt={`Page ${current + 1}`}
            className="block max-w-full max-h-[70vh] object-contain"
            onError={(e) => {
              (e.target as HTMLImageElement).src = "";
              (e.target as HTMLImageElement).alt = "Image not available";
            }}
          />
          {hasReferenceBoxes && (
            <svg
              className="absolute inset-0 h-full w-full pointer-events-none"
              viewBox={`0 0 ${referencePage!.width} ${referencePage!.height}`}
              preserveAspectRatio="none"
              aria-label={`OCR reference boxes from ${ocrReference!.engine}`}
            >
              {referencePage!.boxes.map((box, index) => (
                <rect
                  key={`${box.text}-${index}`}
                  x={box.x}
                  y={box.y}
                  width={box.width}
                  height={box.height}
                  fill="rgba(37, 99, 235, 0.10)"
                  stroke="rgba(37, 99, 235, 0.8)"
                  strokeWidth="1.5"
                >
                  <title>{`${box.text} (${Math.round(box.confidence)}% confidence)`}</title>
                </rect>
              ))}
            </svg>
          )}
        </div>
        {hasReferenceBoxes && (
          <div className="absolute top-2 left-2 bg-blue-700/85 text-white text-xs px-2 py-1 rounded">
            OCR reference · {ocrReference!.engine}
          </div>
        )}
        {pageUrls.length > 1 && (
          <div className="absolute bottom-2 right-2 bg-black/60 text-white text-xs px-2 py-1 rounded">
            {current + 1} / {pageUrls.length}
          </div>
        )}
      </div>

      {pageUrls.length > 1 && (
        <div className="flex gap-2 justify-center flex-wrap">
          {pageUrls.map((_, i) => (
            <button
              key={i}
              onClick={() => setCurrent(i)}
              className={`px-3 py-1 text-sm rounded border transition-colors ${
                i === current
                  ? "bg-blue-600 text-white border-blue-600"
                  : "bg-white text-gray-700 border-gray-300 hover:border-blue-400"
              }`}
            >
              Page {i + 1}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
