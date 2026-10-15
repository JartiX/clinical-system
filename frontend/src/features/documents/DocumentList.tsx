import { Badge, Group, NavLink, Paper, ScrollArea, SegmentedControl, Stack, Text } from "@mantine/core";
import { IconCalendarOff } from "@tabler/icons-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { DocumentSummary } from "../../api/types";
import { formatDate } from "../../lib/format";

type Filter = "all" | "review" | "nodate";

interface Props {
  code: string;
  docs: DocumentSummary[];
  selectedId?: string;
  /** Своя прокрутка списка — на широком экране, где он стоит рядом с документом. */
  scrollable?: boolean;
}

export function DocumentList({ code, docs, selectedId, scrollable }: Props) {
  const [filter, setFilter] = useState<Filter>("all");
  const noDate = docs.filter((d) => !d.doc_date).length;
  const review = docs.filter((d) => d.needs_review).length;
  const shown = docs.filter((d) => (filter === "review" ? d.needs_review : filter === "nodate" ? !d.doc_date : true));

  // выбранный документ всегда виден в списке, даже если он в конце прокрутки
  const listRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!selectedId) return;
    listRef.current?.querySelector(`[data-doc-id="${selectedId}"]`)?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  const items: ReactNode = (
    <>
      {shown.length === 0 && (
        <Text size="sm" c="dimmed" p="sm">
          Нет документов.
        </Text>
      )}
      {shown.map((d) => (
        <NavLink
          key={d.id}
          component={Link}
          to={`/patients/${encodeURIComponent(code)}/documents/${d.id}`}
          active={d.id === selectedId}
          data-doc-id={d.id}
          styles={{ label: { whiteSpace: "normal" }, description: { whiteSpace: "normal" } }}
          label={
            <Group gap={6} align="center">
              <Text size="sm" fw={500} component="span">
                {d.title}
              </Text>
              {d.needs_review && (
                <Badge size="xs" color="orange" variant="light">
                  проверить
                </Badge>
              )}
            </Group>
          }
          description={
            <Group gap={6} component="span">
              {d.doc_date ? (
                <Text size="xs" ff="monospace" component="span">
                  {formatDate(d.doc_date)}
                </Text>
              ) : (
                <Group gap={2} component="span">
                  <IconCalendarOff size={12} color="var(--mantine-color-red-6)" />
                  <Text size="xs" c="red" component="span">
                    нет даты
                  </Text>
                </Group>
              )}
              <Text size="xs" c="dimmed" component="span">
                {d.doc_type_label}
                {d.specialty_label ? ` · ${d.specialty_label}` : ""}
              </Text>
            </Group>
          }
        />
      ))}
    </>
  );

  return (
    <Paper withBorder p="xs" ref={listRef}>
      <Stack gap="xs">
        <SegmentedControl
          fullWidth
          size="xs"
          value={filter}
          onChange={(v) => setFilter(v as Filter)}
          data={[
            { value: "all", label: `Все · ${docs.length}` },
            { value: "review", label: `Проверить · ${review}` },
            { value: "nodate", label: `Без даты · ${noDate}` },
          ]}
        />
        {scrollable ? (
          <ScrollArea.Autosize mah="calc(100dvh - 300px)" scrollbars="y" type="auto">
            {items}
          </ScrollArea.Autosize>
        ) : (
          items
        )}
      </Stack>
    </Paper>
  );
}
