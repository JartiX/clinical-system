import { Badge, Card, Group, Loader, Paper, Stack, Table, Text } from "@mantine/core";
import { useParams } from "react-router-dom";
import { useHistory, useVocabulary } from "../../api/queries";
import type { Activity, ActivityKind, VocabularyEntry } from "../../api/types";
import { formatDate, formatDateTime } from "../../lib/format";
import { useIsCompact } from "../../lib/useIsMobile";

const KINDS: Record<ActivityKind, { label: string; color: string }> = {
  ingest: { label: "приём файлов", color: "indigo" },
  manual_edit: { label: "правка", color: "grape" },
  retract: { label: "отзыв файла", color: "orange" },
  restore: { label: "возврат файла", color: "teal" },
  delete: { label: "удаление файла", color: "red" },
};

const AGENTS: Record<string, string> = { web: "интерфейс", api: "интерфейс", cli: "командная строка" };

const FIELD_LABELS: Record<string, string> = { doc_date: "дата", doc_type: "вид", specialty: "специальность" };

// поле правки -> вид справочника, из которого берутся подписи
const FIELD_KINDS: Record<string, string> = { doc_type: "document_type", specialty: "specialty" };

function describe(a: Activity, vocabulary: VocabularyEntry[]): string {
  switch (a.kind) {
    case "manual_edit": {
      const show = (field: string, value: string | null) => {
        if (value === null) return "—";
        if (field === "doc_date") return formatDate(value);
        return vocabulary.find((v) => v.kind === FIELD_KINDS[field] && v.code === value)?.label ?? value;
      };
      const changes = Object.entries(a.changes ?? {})
        .map(([field, [from, to]]) => `${FIELD_LABELS[field] ?? field}: ${show(field, from)} → ${show(field, to)}`)
        .join("; ");
      return `${a.title ?? ""}: ${changes}`;
    }
    case "retract":
      return `«${a.file}», документов: ${a.affected_documents ?? 0}. Причина: ${a.reason ?? "—"}`;
    case "restore":
      return `«${a.file}», документов: ${a.affected_documents ?? 0}`;
    case "delete":
      return `«${a.file}», удалено документов: ${a.affected_documents ?? 0}. Причина: ${a.reason ?? "—"}`;
    default: {
      const t = a.totals;
      return `файлов ${t.files ?? 0}, новых документов ${t.documents_created ?? 0}, новых версий ${
        t.documents_new_version ?? 0
      }, измерений ${t.measurements ?? 0}`;
    }
  }
}

/** Все действия над данными пациента: приёмы файлов, правки, отзыв и удаление файлов. */
export function HistoryPage() {
  const { code = "" } = useParams();
  const { data, isLoading, error } = useHistory(code);
  const { data: vocabulary = [] } = useVocabulary();
  const compact = useIsCompact();

  if (isLoading) return <Loader />;
  if (error) return <Text c="red">{error.message}</Text>;
  const rows = data ?? [];

  if (compact) {
    return (
      <Stack gap="sm">
        {rows.map((a) => (
          <Card key={a.id} withBorder padding="sm">
            <Group justify="space-between" gap="xs" mb={4}>
              <Badge variant="light" color={KINDS[a.kind].color}>
                {KINDS[a.kind].label}
              </Badge>
              <Text size="xs" c="dimmed">
                {formatDateTime(a.started_at)} · {AGENTS[a.agent] ?? a.agent}
              </Text>
            </Group>
            <Text size="sm">{describe(a, vocabulary)}</Text>
          </Card>
        ))}
      </Stack>
    );
  }

  return (
    <Paper withBorder>
      <Table highlightOnHover verticalSpacing="xs">
        <Table.Thead>
          <Table.Tr>
            <Table.Th style={{ whiteSpace: "nowrap" }}>Когда</Table.Th>
            <Table.Th>Действие</Table.Th>
            <Table.Th>Откуда</Table.Th>
            <Table.Th>Что изменилось</Table.Th>
          </Table.Tr>
        </Table.Thead>
        <Table.Tbody>
          {rows.map((a) => (
            <Table.Tr key={a.id}>
              <Table.Td style={{ whiteSpace: "nowrap" }}>{formatDateTime(a.started_at)}</Table.Td>
              <Table.Td>
                <Badge variant="light" color={KINDS[a.kind].color}>
                  {KINDS[a.kind].label}
                </Badge>
              </Table.Td>
              <Table.Td>{AGENTS[a.agent] ?? a.agent}</Table.Td>
              <Table.Td>
                <Text size="sm">{describe(a, vocabulary)}</Text>
              </Table.Td>
            </Table.Tr>
          ))}
        </Table.Tbody>
      </Table>
    </Paper>
  );
}
