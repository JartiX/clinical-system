import { Alert, Badge, Button, Card, Group, Loader, Paper, Stack, Table, Text } from "@mantine/core";
import { IconArrowBackUp, IconFileOff, IconInfoCircle, IconTrash } from "@tabler/icons-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useFiles } from "../../api/queries";
import type { SourceFileRow } from "../../api/types";
import { formatDateTime } from "../../lib/format";
import { useIsCompact } from "../../lib/useIsMobile";
import { DeleteFileModal, RestoreFileModal, RetractFileModal } from "./FileActionModals";

type Action = { kind: "retract" | "restore" | "delete"; file: SourceFileRow } | null;

const formatSize = (bytes: number) => (bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} КБ` : `${(bytes / 1024 / 1024).toFixed(1)} МБ`);

function outcome(f: SourceFileRow): string {
  const parts = [`документов: ${f.status === "active" ? f.documents_current : f.documents}`];
  if (f.facts_current) parts.push(`измерений: ${f.facts_current}`);
  return parts.join(", ");
}

function StatusBadge({ f }: { f: SourceFileRow }) {
  return f.status === "active" ? (
    <Badge color="green" variant="light">
      используется
    </Badge>
  ) : (
    <Badge color="gray" variant="light">
      отозван
    </Badge>
  );
}

function Actions({ f, onAction }: { f: SourceFileRow; onAction: (a: Action) => void }) {
  return (
    <Group gap="xs">
      {f.status === "active" ? (
        <Button
          size="xs"
          variant="default"
          leftSection={<IconFileOff size={14} />}
          onClick={() => onAction({ kind: "retract", file: f })}
        >
          Отозвать
        </Button>
      ) : (
        <Button
          size="xs"
          variant="default"
          leftSection={<IconArrowBackUp size={14} />}
          onClick={() => onAction({ kind: "restore", file: f })}
        >
          Вернуть
        </Button>
      )}
      <Button
        size="xs"
        variant="subtle"
        color="red"
        leftSection={<IconTrash size={14} />}
        onClick={() => onAction({ kind: "delete", file: f })}
      >
        Удалить
      </Button>
    </Group>
  );
}

/** Исходные файлы пациента и то, что из них получено. Отзыв убирает файл целиком, со всеми документами. */
export function FilesPage() {
  const { code = "" } = useParams();
  const { data, isLoading, error } = useFiles(code);
  const compact = useIsCompact();
  const [action, setAction] = useState<Action>(null);

  if (isLoading) return <Loader />;
  if (error) return <Text c="red">{error.message}</Text>;
  const files = data ?? [];

  return (
    <Stack gap="md">
      <Alert variant="light" color="blue" icon={<IconInfoCircle />}>
        Если загружен не тот файл, отзовите его: из системы уберётся всё, что из него получено (например, все визиты из
        саммари). Отзыв можно отменить. Удаляйте безвозвратно только данные, которые вообще не должны были попасть в
        карту, например файл другого человека.
      </Alert>

      {files.length === 0 && <Text c="dimmed">Файлов нет.</Text>}

      {compact ? (
        <Stack gap="sm">
          {files.map((f) => (
            <Card key={f.id} withBorder padding="sm">
              <Stack gap={6}>
                <Group justify="space-between" align="flex-start" gap="xs">
                  <Text fw={500} style={{ flex: 1, minWidth: 0 }}>
                    {f.file_name}
                  </Text>
                  <StatusBadge f={f} />
                </Group>
                <Text size="sm" c="dimmed">
                  {formatDateTime(f.received_at)} · {formatSize(f.size)} · {outcome(f)}
                </Text>
                {f.status_reason && <Text size="sm">Причина отзыва: {f.status_reason}</Text>}
                <Actions f={f} onAction={setAction} />
              </Stack>
            </Card>
          ))}
        </Stack>
      ) : (
        files.length > 0 && (
          <Paper withBorder>
            <Table verticalSpacing="sm" highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Файл</Table.Th>
                  <Table.Th>Загружен</Table.Th>
                  <Table.Th>Что получено</Table.Th>
                  <Table.Th>Состояние</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {files.map((f) => (
                  <Table.Tr key={f.id} style={{ opacity: f.status === "active" ? 1 : 0.7 }}>
                    <Table.Td>
                      <Text size="sm" fw={500}>
                        {f.file_name}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {formatSize(f.size)}
                      </Text>
                    </Table.Td>
                    <Table.Td style={{ whiteSpace: "nowrap" }}>{formatDateTime(f.received_at)}</Table.Td>
                    <Table.Td>{outcome(f)}</Table.Td>
                    <Table.Td style={{ whiteSpace: "nowrap" }}>
                      <StatusBadge f={f} />
                      {f.status_reason && (
                        <Text size="xs" c="dimmed" mt={4}>
                          {f.status_reason}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Actions f={f} onAction={setAction} />
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Paper>
        )
      )}

      {action?.kind === "retract" && <RetractFileModal file={action.file} onClose={() => setAction(null)} />}
      {action?.kind === "restore" && <RestoreFileModal file={action.file} onClose={() => setAction(null)} />}
      {action?.kind === "delete" && <DeleteFileModal file={action.file} onClose={() => setAction(null)} />}
    </Stack>
  );
}
