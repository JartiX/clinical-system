import { useMatches } from "@mantine/core";

/** Узкий экран (телефон): уже брейкпоинта sm в Mantine (48em). */
export function useIsMobile(): boolean {
  return useMatches({ base: true, sm: false }) ?? false;
}

/** Экран, на котором таблицы с несколькими колонками не помещаются: уже брейкпоинта md (62em). */
export function useIsCompact(): boolean {
  return useMatches({ base: true, md: false }) ?? false;
}
