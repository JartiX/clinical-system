import dayjs from "dayjs";
import customParseFormat from "dayjs/plugin/customParseFormat";
import "dayjs/locale/ru";
import { sha256Bytes } from "./sha256";

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
  const data = await file.arrayBuffer();
  // crypto.subtle есть только по HTTPS и на localhost; по обычному HTTP считаем сами
  if (!globalThis.crypto?.subtle) return sha256Bytes(new Uint8Array(data));
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

/** Замечание о дате, которое снимается вводом даты вручную. */
export const DATE_NOTE_CODES = new Set(["missing_date", "date_from_header", "invalid_header_date"]);

/** Ключ сравнения имён — как normalize() на сервере: без учёта регистра, ё/е, кавычек и пробелов. */
export const nameKey = (text: string) =>
  text
    .normalize("NFKC")
    .toLowerCase()
    .replace(/ё/g, "е")
    .replace(/_/g, " ")
    .replace(/[«»]/g, '"')
    .replace(/\s+/g, " ")
    .trim();

/** «1 строка», «3 строки», «5 строк». */
export function plural(n: number, one: string, few: string, many: string): string {
  const d10 = n % 10;
  const d100 = n % 100;
  const word = d10 === 1 && d100 !== 11 ? one : d10 >= 2 && d10 <= 4 && (d100 < 12 || d100 > 14) ? few : many;
  return `${n} ${word}`;
}
