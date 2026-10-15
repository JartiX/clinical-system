import { Alert, Anchor, Badge, Box, Group, Loader, Paper, Stack, Text, Title, Tooltip } from "@mantine/core";
import { IconFileOff, IconHistory } from "@tabler/icons-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useDocument } from "../../api/queries";
import type { DocumentDetail } from "../../api/types";
import { ReviewNotes } from "../../components/ReviewNotes";
import { dataClassLabel, formatDateTime } from "../../lib/format";
import { DocumentMetaForm } from "./DocumentMetaForm";
import classes from "./DocumentView.module.css";

export function DocumentView({ id, code }: { id: string; code: string }) {
  const { data: doc, isLoading, error } = useDocument(id);
  const base = `/patients/${encodeURIComponent(code)}`;

  if (isLoading) return <Loader />;
  if (error || !doc) return <Text c="red">{error?.message ?? "Документ не найден"}</Text>;

  const retracted = doc.source_file_status === "retracted";

  return (
    <Paper withBorder p={{ base: "sm", sm: "md" }}>
      <Stack gap="sm">
        <Stack gap={4}>
          <Title order={3} fz={{ base: "h4", sm: "h3" }}>
            {doc.title}
          </Title>
          <Text size="sm" c="dimmed">
            Из файла{" "}
            <Anchor component={Link} to={`${base}/files`} size="sm">
              «{doc.file_name}»
            </Anchor>{" "}
            · {dataClassLabel(doc.data_class)}
          </Text>
          <Versions doc={doc} base={base} />
        </Stack>

        {retracted && (
          <Alert color="gray" icon={<IconFileOff />} title="Файл отозван">
            Документ не используется: исходный файл отозван. Вернуть его можно во вкладке «Файлы».
          </Alert>
        )}
        {!retracted && !doc.is_current && (
          <Alert color="gray" icon={<IconHistory />}>
            Это прежняя версия документа, править её нельзя.
          </Alert>
        )}

        <ReviewNotes notes={doc.review_notes} />
        <DocumentMetaForm doc={doc} code={code} />
        <DocumentText doc={doc} />
      </Stack>
    </Paper>
  );
}

function Versions({ doc, base }: { doc: DocumentDetail; base: string }) {
  if (doc.versions.length < 2) return null;
  return (
    <Group gap={4}>
      <Text size="xs" c="dimmed">
        Версии:
      </Text>
      {doc.versions.map((v) => (
        <Tooltip key={v.id} label={`${formatDateTime(v.created_at)}${v.is_current ? " · текущая" : ""}`}>
          <Badge
            component={Link}
            to={`${base}/documents/${v.id}`}
            variant={v.id === doc.id ? "filled" : "light"}
            color={v.is_current ? "indigo" : "gray"}
            style={{ cursor: "pointer" }}
          >
            v{v.version}
          </Badge>
        </Tooltip>
      ))}
    </Group>
  );
}

/** Текст документа по фрагментам; при наведении подсвечивается фрагмент и видны его границы. */
function DocumentText({ doc }: { doc: DocumentDetail }) {
  const [hover, setHover] = useState<string | null>(null);
  return (
    <Box className={classes.text}>
      {doc.fragments.map((f) => (
        <div
          key={f.id}
          className={classes.fragment}
          data-kind={f.kind}
          data-hover={hover === f.id || undefined}
          onMouseEnter={() => setHover(f.id)}
          onMouseLeave={() => setHover(null)}
          title={`Фрагмент ${f.ordinal} · символы ${f.start}–${f.end}`}
        >
          {doc.text.slice(f.start, f.end)}
        </div>
      ))}
    </Box>
  );
}
