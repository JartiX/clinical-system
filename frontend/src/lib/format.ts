import dayjs from "dayjs";
import customParseFormat from "dayjs/plugin/customParseFormat";
import "dayjs/locale/ru";

// без плагина DateInput не разбирает дату, введённую с клавиатуры («20.10.2025»)
dayjs.extend(customParseFormat);
dayjs.locale("ru");

export const formatDate = (iso: string | null | undefined) => (iso ? dayjs(iso).format("DD.MM.YYYY") : "—");

export const formatDateTime = (iso: string | null | undefined) => (iso ? dayjs(iso).format("DD.MM.YYYY HH:mm") : "—");

export const DATE_SOURCE_LABELS: Record<string, string> = {
  filename: "из имени файла",
  header: "из заголовка документа",
  table: "из таблицы",
  manual: "указана вручную",
  none: "не указана",
};

export const DATA_CLASS_OPTIONS = [
  { value: "synthetic", label: "Синтетические" },
  { value: "deidentified", label: "Обезличенные" },
  { value: "personal", label: "Персональные" },
];

export const dataClassLabel = (code: string) => DATA_CLASS_OPTIONS.find((o) => o.value === code)?.label ?? code;

/** SHA-256 содержимого файла в hex — чтобы заранее узнать, загружался ли уже такой файл. */
export async function sha256(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Замечание о дате, которое снимается вводом даты вручную. */
export const DATE_NOTE_CODES = new Set(["missing_date", "date_from_header", "invalid_header_date"]);
