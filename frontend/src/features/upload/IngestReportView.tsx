import { Accordion, Badge, Group, Stack, Text } from "@mantine/core";
import type { ReportFile, UploadResult } from "../../api/types";
import { formatDate } from "../../lib/format";
import { MissingDates } from "./MissingDates";

const STATUS: Record<ReportFile["status"], { label: string; color: string }> = {
  processed: { label: "принят", color: "green" },
  unchanged: { label: "без изменений", color: "gray" },
  skipped: { label: "пропущен", color: "red" },
};

const ACTION: Record<string, string> = { created: "новый", new_version: "новая версия", unchanged: "без изменений" };

export function IngestReportView({ result }: { result: UploadResult }) {
  const t = result.report.totals;
  return (
    <Stack>
      <Group gap="xs">
        <Badge variant="light">файлов {t.files}</Badge>
        <Badge variant="light" color="green">
          новых документов {t.documents_created}
        </Badge>
        <Badge variant="light" color="blue">
          новых версий {t.documents_new_version}
        </Badge>
        <Badge variant="light" color="gray">
          без изменений {t.files_unchanged}
        </Badge>
        <Badge variant="light" color="grape">
          измерений {t.measurements}
        </Badge>
        {t.needs_review > 0 && (
          <Badge variant="light" color="orange">
            на проверку {t.needs_review}
          </Badge>
        )}
      </Group>

      <MissingDates report={result.report} />

      <Accordion multiple variant="separated" defaultValue={result.report.files.filter((f) => f.issues.length).map((f) => f.file)}>
        {result.report.files.map((f) => (
          <Accordion.Item key={f.file} value={f.file}>
            <Accordion.Control>
              <Group gap="xs" wrap="nowrap" align="flex-start">
                <Badge color={STATUS[f.status].color} variant="light" style={{ flexShrink: 0 }}>
                  {STATUS[f.status].label}
                </Badge>
                <Text size="sm" style={{ minWidth: 0 }}>
                  {f.file}
                  {f.renamed_from && (
                    <Text span size="xs" c="dimmed">
                      {" "}
                      (загружен как «{f.renamed_from}»)
                    </Text>
                  )}
                </Text>
              </Group>
            </Accordion.Control>
            <Accordion.Panel>
              <Stack gap={4} style={{ overflowWrap: "anywhere" }}>
                {f.issues.map((i) => (
                  <Text size="sm" key={i} c="red">
                    {i}
                  </Text>
                ))}
                {(f.unmapped_columns ?? []).map((c) => (
                  <Text size="sm" key={c} c="orange">
                    колонка не распознана: {c}
                  </Text>
                ))}
                {(f.skipped_rows ?? []).map((r) => (
                  <Text size="sm" key={r} c="dimmed">
                    {r}
                  </Text>
                ))}
                {f.documents.map((d) => (
                  <div key={d.id}>
                    <Text size="sm">
                      {formatDate(d.date)} · {d.title} · {ACTION[d.action]}
                      {d.measurements > 0 && `, измерений ${d.measurements}`}
                    </Text>
                    {d.notes.map((n) => (
                      <Text key={n.code + n.text} size="xs" c="orange">
                        {n.text}
                      </Text>
                    ))}
                  </div>
                ))}
                {(f.retired ?? []).map((r) => (
                  <Text size="sm" key={r} c="dimmed">
                    больше не текущий: {r}
                  </Text>
                ))}
              </Stack>
            </Accordion.Panel>
          </Accordion.Item>
        ))}
      </Accordion>
    </Stack>
  );
}
