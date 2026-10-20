import { Alert, Button, Group, Stack, Text } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { notifications } from "@mantine/notifications";
import { IconCalendarQuestion } from "@tabler/icons-react";
import { useState } from "react";
import { useUpdateDocument } from "../../api/queries";
import type { IngestReport } from "../../api/types";
import { DATE_NOTE_CODES } from "../../lib/format";

/** Документы из отчёта, у которых дата не найдена или требует проверки: дату можно указать сразу. */
export function MissingDates({ report }: { report: IngestReport }) {
  const update = useUpdateDocument();
  const candidates = report.files
    .flatMap((f) => f.documents)
    .filter((d) => d.action !== "unchanged" && d.notes.some((n) => DATE_NOTE_CODES.has(n.code)));
  const [dates, setDates] = useState<Record<string, string | null>>(() =>
    Object.fromEntries(candidates.map((d) => [d.id, d.date])),
  );
  const [saved, setSaved] = useState<Set<string>>(new Set());

  const pending = candidates.filter((d) => !saved.has(d.id));
  const changed = pending.filter((d) => dates[d.id] && dates[d.id] !== d.date);
  if (!candidates.length) return null;

  const save = async () => {
    try {
      for (const d of changed) {
        await update.mutateAsync({ id: d.id, patch: { doc_date: dates[d.id] } });
        setSaved((prev) => new Set(prev).add(d.id));
      }
      notifications.show({ color: "green", message: `Сохранено дат: ${changed.length}` });
    } catch (e) {
      notifications.show({ color: "red", title: "Не сохранено", message: String((e as Error).message) });
    }
  };

  return (
    <Alert color="orange" icon={<IconCalendarQuestion />} title="Укажите даты документов">
      <Stack gap="xs">
        <Text size="sm">
          Даты нужны, чтобы привязать к календарю сведения вроде «месяц назад». Можно пропустить и указать позже в
          карточке документа.
        </Text>
        {candidates.map((d) => (
          <Group key={d.id} justify="space-between" gap="xs">
            <Text size="sm" style={{ flex: "1 1 12rem", minWidth: 0 }}>
              {d.title}
            </Text>
            {saved.has(d.id) ? (
              <Text size="sm" c="green">
                сохранено
              </Text>
            ) : (
              <DateInput
                w={{ base: "100%", xs: 170 }}
                size="xs"
                placeholder="ДД.ММ.ГГГГ"
                valueFormat="DD.MM.YYYY"
                value={dates[d.id]}
                onChange={(v) => setDates({ ...dates, [d.id]: v })}
                clearable
              />
            )}
          </Group>
        ))}
        {pending.length > 0 && (
          <Group justify="flex-end">
            <Button size="xs" onClick={save} loading={update.isPending} disabled={!changed.length}>
              Сохранить даты
            </Button>
          </Group>
        )}
      </Stack>
    </Alert>
  );
}
