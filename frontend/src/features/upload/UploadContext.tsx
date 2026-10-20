import { createContext, useContext, useState, type ReactNode } from "react";
import { UploadModal } from "./UploadModal";

interface UploadApi {
  /** Открыть окно загрузки; код пациента подставляется, если передан. */
  open: (patientCode?: string) => void;
}

const UploadCtx = createContext<UploadApi>({ open: () => {} });

export const useUpload = () => useContext(UploadCtx);

export function UploadProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ opened: boolean; code: string }>({ opened: false, code: "" });
  return (
    <UploadCtx.Provider value={{ open: (code) => setState({ opened: true, code: code ?? "" }) }}>
      {children}
      {state.opened && (
        <UploadModal initialCode={state.code} onClose={() => setState({ opened: false, code: "" })} />
      )}
    </UploadCtx.Provider>
  );
}
