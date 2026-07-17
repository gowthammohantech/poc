"use client";

import { useCallback, useRef, useState } from "react";

interface FileDropzoneProps {
  accept: string;
  file: File | null;
  onFileSelected: (file: File | null) => void;
  label: string;
  hint: string;
  activeColor?: "emerald" | "blue";
}

const ACTIVE_CLASSES = {
  emerald: "border-emerald-500 bg-emerald-50",
  blue: "border-blue-500 bg-blue-50",
};

const HOVER_CLASSES = {
  emerald: "border-gray-300 hover:border-emerald-400",
  blue: "border-gray-300 hover:border-blue-400",
};

export default function FileDropzone({ accept, file, onFileSelected, label, hint, activeColor = "emerald" }: FileDropzoneProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const f = e.dataTransfer.files[0];
      if (f) onFileSelected(f);
    },
    [onFileSelected]
  );

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      onClick={() => fileRef.current?.click()}
      className={`border-2 border-dashed rounded-lg p-10 text-center cursor-pointer transition-colors ${
        dragging ? ACTIVE_CLASSES[activeColor] : HOVER_CLASSES[activeColor]
      }`}
    >
      <input
        ref={fileRef}
        type="file"
        className="hidden"
        accept={accept}
        onChange={(e) => onFileSelected(e.target.files?.[0] || null)}
      />
      {file ? (
        <div>
          <p className="font-medium text-gray-800">{file.name}</p>
          <p className="text-sm text-gray-500 mt-1">{(file.size / 1024).toFixed(1)} KB</p>
        </div>
      ) : (
        <div>
          <p className="text-gray-500">{label}</p>
          <p className="text-sm text-gray-400 mt-2">{hint}</p>
        </div>
      )}
    </div>
  );
}
