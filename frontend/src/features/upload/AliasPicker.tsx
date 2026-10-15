import { Alert, Checkbox, Loader, Group, Stack, Text } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import type { TableNames } from "../../api/types";
import { nameKey, plural } from "../../lib/format";

interface Props {
  tables: TableNames[] | null;
  loading: boolean;
  /** имена, уже сохранённые у пациента: сервер применяет их всегда */
  known: string[];
  selected: string[];
  onChange: (names: string[]) => void;
}

interface FoundName {
  name: string;
  rows: number;
  files: string[];
}

/** Имена из всех таблиц, совпадающие по ключу сравнения, — одно имя. */
export function mergeNames(tables: TableNames[]): FoundName[] {
  const byKey = new Map<string, FoundName>();
  for (const t of tables) {
    for (const n of t.names) {
      const item = byKey.get(nameKey(n.name)) ?? { name: n.name, rows: 0, files: [] };
      item.rows += n.rows;
      item.files.push(t.file);
      byKey.set(nameKey(n.name), item);
    }
  }
  return [...byKey.values()];
}

const rowsText = (n: number) => plural(n, "строка", "строки", "строк");

/** Выбор, чьи ответы брать из таблиц опросников: имена читаются из самих таблиц. */
export function AliasPicker({ tables, loading, known, selected, onChange }: Props) {
  if (loading) {
    return (
      <Group gap="xs">
        <Loader size="xs" />
        <Text size="sm" c="dimmed">
          Читаю имена из таблиц опросников…
        </Text>
      </Group>
    );
  }
  if (!tables || tables.length === 0) return null;

  const found = mergeNames(tables);
  const knownKeys = new Set(known.map(nameKey));
  const active = new Set([...knownKeys, ...selected.map(nameKey)]);
  const several = tables.length > 1;

  const toggle = (name: string, on: boolean) =>
    onChange(on ? [...selected, name] : selected.filter((s) => nameKey(s) !== nameKey(name)));

  const warnings: string[] = [];
  for (const t of tables) {
    if (t.error) {
      warnings.push(`«${t.file}»: ${t.error}`);
    } else if (!t.has_name_column) {
      warnings.push(`В «${t.file}» нет колонки с именем — будут взяты все строки (${t.unnamed_rows}).`);
    } else if (active.size > 0) {
      if (t.names.length > 0 && !t.names.some((n) => active.has(nameKey(n.name)))) {
        warnings.push(`В «${t.file}» нет строк выбранных людей — из этой таблицы ничего не загрузится.`);
      } else if (t.unnamed_rows > 0) {
        warnings.push(`В «${t.file}» пропускаются строки без имени: ${t.unnamed_rows}.`);
      }
    }
  }
  if (active.size === 0 && found.length > 1) {
    warnings.push(`Никто не выбран — в карту попадут ответы всех людей из таблиц (${found.length}).`);
  }

  return (
    <Stack gap="xs">
      <div>
        <Text size="sm" fw={500}>
          Чьи ответы брать из опросников
        </Text>
        <Text size="xs" c="dimmed">
          Имена из колонки «Имя» в таблицах. Выбранные запомнятся у пациента и в следующий раз применятся сами.
        </Text>
      </div>
      {found.length > 0 && (
        <Stack gap={6}>
          {found.map((n) => {
            const isKnown = knownKeys.has(nameKey(n.name));
            const details = [rowsText(n.rows)];
            if (several) details.push(n.files.join(", "));
            if (isKnown) details.push("уже сохранено у пациента");
            return (
              <Checkbox
                key={nameKey(n.name)}
                label={n.name}
                description={details.join(" · ")}
                checked={active.has(nameKey(n.name))}
                disabled={isKnown}
                onChange={(e) => toggle(n.name, e.currentTarget.checked)}
              />
            );
          })}
        </Stack>
      )}
      {warnings.length > 0 && (
        <Alert color="yellow" icon={<IconAlertTriangle />} p="xs">
          <Stack gap={4}>
            {warnings.map((w) => (
              <Text key={w} size="sm">
                {w}
              </Text>
            ))}
          </Stack>
        </Alert>
      )}
    </Stack>
  );
}
