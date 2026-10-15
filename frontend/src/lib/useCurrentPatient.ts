import { useMatch } from "react-router-dom";

/** Код пациента из адреса. Работает и в общем макете, где useParams не видит вложенные маршруты. */
export function useCurrentPatientCode(): string | undefined {
  const match = useMatch("/patients/:code/*");
  return match?.params.code;
}
