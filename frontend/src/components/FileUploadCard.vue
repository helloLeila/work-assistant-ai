<script setup lang="ts">
const props = defineProps<{
  loading?: boolean;
}>();

const emit = defineEmits<{
  select: [file: File];
}>();

function onChange(event: Event): void {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) {
    return;
  }
  emit("select", file);
  input.value = "";
}
</script>

<template>
  <section class="glass-panel rounded-[30px] p-5">
    <div
      class="rounded-[26px] border border-dashed border-rose-300 bg-rose-50/70 p-6 text-center"
    >
      <p class="text-sm font-semibold text-rose-700">
        上传知识文档
      </p>
      <p class="mt-2 text-sm leading-6 text-slate-600">
        支持 PDF、DOCX 和 TXT。上传后系统会完成分块、索引和检索准备。
      </p>
      <label
        class="mt-4 inline-flex cursor-pointer items-center justify-center rounded-2xl bg-rose-600 px-4 py-3 text-sm font-semibold text-white transition hover:bg-rose-700"
      >
        {{ props.loading ? "上传中..." : "选择文件" }}
        <input
          class="hidden"
          type="file"
          accept=".pdf,.doc,.docx,.txt"
          :disabled="props.loading"
          @change="onChange"
        />
      </label>
    </div>
  </section>
</template>
