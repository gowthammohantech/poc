"use client";

import { useState } from "react";
import { getPageImageUrl } from "@/lib/api";

interface PagePreviewProps {
  pageUrls: string[];
}

export default function PagePreview({ pageUrls }: PagePreviewProps) {
  const [current, setCurrent] = useState(0);

  if (!pageUrls || pageUrls.length === 0) {
    return (
      <div className="flex items-center justify-center h-96 bg-gray-100 rounded-lg">
        <p className="text-gray-500">No pages available</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="relative bg-gray-100 rounded-lg overflow-hidden" style={{ minHeight: "500px" }}>
        <img
          src={getPageImageUrl(pageUrls[current])}
          alt={`Page ${current + 1}`}
          className="w-full object-contain max-h-[70vh]"
          onError={(e) => {
            (e.target as HTMLImageElement).src = "";
            (e.target as HTMLImageElement).alt = "Image not available";
          }}
        />
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
