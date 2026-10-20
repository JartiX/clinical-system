import { Button, Group, Paper, Select, SimpleGrid, Stack, Text } from "@mantine/core";
import { DateInput } from "@mantine/dates";
import { notifications } from "@mantine/notifications";
import { IconDeviceFloppy } from "@tabler/icons-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useUpdateDocument, useVocabularyOptions } from "../../api/queries";
import type { DocumentDetail, DocumentPatch } from "../../api/types";
import { DATE_SOURCE_LABELS } from "../../lib/format";

/** Дата, вид документа и специальность автора. Сохранение создаёт новую версию документа. */
export function DocumentMetaForm({ doc, code }: { doc: DocumentDetail; code: string }) {
  const navigate = useNavigate();
  const update = useUpdateDocument();
  const typeOptions = useVocabularyOptions("document_type");
  const specialtyOptions = useVocabularyOptions("specialty");

  const [date, setDate] = useState<string | null>(doc.doc_date);
  const [docType, setDocType] = useState<string>(doc.doc_type);
  const [specialty, setSpecialty] = useState<string | null>(doc.specialty);

  const tableDate = doc.date_source === "table";
  const editable = doc.is_current && doc.source_file_status === "active";

  const patch: DocumentPatch = {};
  if (date !== doc.doc_date) patch.doc_date = date;
  if (docType !== doc.doc_type) patch.doc_type = docType;
  if (specialty !== doc.specialty) patch.specialty = specialty;
  const dirty = Object.keys(patch).length > 0;

  const save = async () => {
    try {
      const updated = await update.mutateAsync({ id: doc.id, patch });
      notifications.show({ color: "green", message: `Сохранено, документ теперь в версии ${updated.version}` });
      navigate(`/patients/${encodeURIComponent(code)}/documents/${updated.id}`, { replace: true });
    } catch (e) {
      notifications.show({ color: "red", title: "Не сохранено", message: String((e as Error).message) });
    }
  };

  return (
    <Paper withBorder p="sm" bg="var(--mantine-color-default-hover)">
      <Stack gap="sm">
        <SimpleGrid cols={{ base: 1, xs: 2, lg: 3 }} spacing="sm">
          <DateInput
            label="Дата документа"
            description={
              tableDate
                ? "берётся из отметок времени в таблице"
                : doc.doc_date
                  ? (DATE_SOURCE_LABELS[doc.date_source] ?? doc.date_source)
                  : "не найдена при загрузке"
            }
            placeholder="ДД.ММ.ГГГГ"
            valueFormat="DD.MM.YYYY"
            value={date}
            onChange={setDate}
            disabled={!editable || tableDate}
            error={!date && !tableDate ? "укажите дату" : undefined}
            clearable
          />
          <Select
            label="Вид документа"
            description="из справочника"
            data={typeOptions}
            value={docType}
            onChange={(v) => v && setDocType(v)}
            allowDeselect={false}
            disabled={!editable}
            searchable
          />
          <Select
            label="Специальность автора"
            description="если известна"
            data={specialtyOptions}
            value={specialty}
            onChange={setSpecialty}
            disabled={!editable}
            clearable
            searchable
            placeholder="не указана"
          />
        </SimpleGrid>
        <Group justify="space-between" gap="sm">
          <Text size="xs" c="dimmed">
            Правка сохраняется новой версией документа, прежняя остаётся в истории.
          </Text>
          <Button
            leftSection={<IconDeviceFloppy size={16} />}
            onClick={save}
            disabled={!dirty || !editable}
            loading={update.isPending}
          >
            Сохранить
          </Button>
        </Group>
      </Stack>
    </Paper>
  );
}
