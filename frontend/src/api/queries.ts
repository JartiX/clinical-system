// Хуки TanStack Query: загрузка данных с кэшем и сброс кэша после изменений

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { enc, http } from "./client";
import type {
  Activity,
  DocumentDetail,
  DocumentPatch,
  DocumentSummary,
  Measurement,
  NameConflict,
  Patient,
  ShaclResult,
  SourceFileRow,
  TableNames,
  UploadResult,
  VocabularyEntry,
} from "./types";

export const keys = {
  patients: ["patients"] as const,
  patient: (code: string) => ["patient", code] as const,
  documents: (code: string) => ["patient", code, "documents"] as const,
  document: (id: string) => ["document", id] as const,
  measurements: (code: string) => ["patient", code, "measurements"] as const,
  history: (code: string) => ["patient", code, "history"] as const,
  files: (code: string) => ["patient", code, "files"] as const,
  vocabulary: ["vocabulary"] as const,
};

export const usePatients = () => useQuery({ queryKey: keys.patients, queryFn: () => http.get<Patient[]>("/api/patients") });

export const useDocuments = (code: string) =>
  useQuery({
    queryKey: keys.documents(code),
    queryFn: () => http.get<DocumentSummary[]>(`/api/patients/${enc(code)}/documents`),
  });

export const useDocument = (id: string | undefined) =>
  useQuery({
    queryKey: keys.document(id ?? ""),
    queryFn: () => http.get<DocumentDetail>(`/api/documents/${id}`),
    enabled: !!id,
  });

export const useMeasurements = (code: string) =>
  useQuery({
    queryKey: keys.measurements(code),
    queryFn: () => http.get<Measurement[]>(`/api/patients/${enc(code)}/measurements`),
  });

export const useHistory = (code: string) =>
  useQuery({
    queryKey: keys.history(code),
    queryFn: () => http.get<Activity[]>(`/api/patients/${enc(code)}/runs`),
  });

export const useVocabulary = () =>
  useQuery({
    queryKey: keys.vocabulary,
    queryFn: () => http.get<VocabularyEntry[]>("/api/vocabulary"),
    staleTime: Infinity,
  });

/** Подписи справочника нужного вида для выпадающих списков. */
export function useVocabularyOptions(kind: string) {
  const { data = [] } = useVocabulary();
  return data.filter((v) => v.kind === kind).map((v) => ({ value: v.code, label: v.label }));
}

export function useUpdateDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: DocumentPatch }) =>
      http.patch<DocumentDetail>(`/api/documents/${id}`, patch),
    onSuccess: (doc) => {
      qc.setQueryData(keys.document(doc.id), doc);
      qc.invalidateQueries({ queryKey: ["patient"] });
      qc.invalidateQueries({ queryKey: keys.patients });
    },
  });
}

/** Имена из колонки имени в таблицах опросников — до загрузки, чтобы выбрать пациента. */
export const previewTableNames = (files: File[]) => {
  const form = new FormData();
  files.forEach((f) => form.append("files", f));
  return http.postForm<{ tables: TableNames[] }>("/api/tables/names", form);
};

export const checkFiles =(code: string, files: { name: string; sha256: string }[]) =>
  http.post<{ conflicts: NameConflict[] }>(`/api/patients/${enc(code)}/files/check`, { files });

export function useUploadFiles() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { code: string; files: File[]; dataClass: string; aliases: string[]; separate: string[] }) => {
      const form = new FormData();
      args.files.forEach((f) => form.append("files", f));
      args.separate.forEach((name) => form.append("separate", name));
      form.append("data_class", args.dataClass);
      args.aliases.forEach((name) => form.append("aliases", name));
      return http.postForm<UploadResult>(`/api/patients/${enc(args.code)}/files`, form);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.patients });
      qc.invalidateQueries({ queryKey: ["patient"] });
    },
  });
}

export const validatePatient = (code: string) => http.get<ShaclResult>(`/api/patients/${enc(code)}/validate`);

export const useFiles = (code: string) =>
  useQuery({
    queryKey: keys.files(code),
    queryFn: () => http.get<SourceFileRow[]>(`/api/patients/${enc(code)}/files`),
  });

/** Отзыв, возврат и удаление файла меняют почти всё у пациента — сбрасываем его кэш целиком. */
function useFileAction<A>(fn: (args: A) => Promise<unknown>) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["patient"] });
      qc.invalidateQueries({ queryKey: ["document"] });
      qc.invalidateQueries({ queryKey: keys.patients });
    },
  });
}

export const useRetractFile = () =>
  useFileAction(({ id, reason }: { id: string; reason: string }) => http.post(`/api/files/${id}/retract`, { reason }));

export const useRestoreFile = () => useFileAction((id: string) => http.post(`/api/files/${id}/restore`, {}));

export const useDeleteFile = () =>
  useFileAction(({ id, reason, confirmName }: { id: string; reason: string; confirmName: string }) =>
    http.post(`/api/files/${id}/delete`, { reason, confirm_name: confirmName }),
  );
