import { describe, it, expect, beforeEach } from "vitest";
import { ref, nextTick, defineComponent, h } from "vue";
import { mount } from "@vue/test-utils";
import { useJsonLd } from "@/composables/useJsonLd";

const SCRIPT_ID = "aracne-jsonld";

function currentPayload(): unknown {
  const el = document.getElementById(SCRIPT_ID);
  if (!el) return null;
  return JSON.parse(el.textContent ?? "null");
}

describe("useJsonLd", () => {
  beforeEach(() => {
    // Isolation: each test starts with no JSON-LD script in <head>.
    document.getElementById(SCRIPT_ID)?.remove();
  });

  it("injects a script tag with the payload on mount", () => {
    const source = ref<object | null>({ "@type": "WebSite", name: "Aracne2" });
    const Comp = defineComponent({
      setup() {
        useJsonLd(source);
        return () => h("div");
      },
    });
    mount(Comp);
    const el = document.getElementById(SCRIPT_ID) as HTMLScriptElement | null;
    expect(el).not.toBeNull();
    expect(el?.type).toBe("application/ld+json");
    expect(currentPayload()).toEqual({ "@type": "WebSite", name: "Aracne2" });
  });

  it("does not inject anything while the source is null", () => {
    const source = ref<object | null>(null);
    const Comp = defineComponent({
      setup() {
        useJsonLd(source);
        return () => h("div");
      },
    });
    mount(Comp);
    expect(document.getElementById(SCRIPT_ID)).toBeNull();
  });

  it("installs the script once the source resolves from null to a value", async () => {
    const source = ref<object | null>(null);
    const Comp = defineComponent({
      setup() {
        useJsonLd(source);
        return () => h("div");
      },
    });
    mount(Comp);
    expect(document.getElementById(SCRIPT_ID)).toBeNull();
    source.value = { "@type": "CreativeWork", name: "A collection" };
    await nextTick();
    expect(currentPayload()).toEqual({ "@type": "CreativeWork", name: "A collection" });
  });

  it("updates the same script tag when the source changes (no stacking)", async () => {
    const source = ref<object | null>({ "@type": "WebSite", name: "v1" });
    const Comp = defineComponent({
      setup() {
        useJsonLd(source);
        return () => h("div");
      },
    });
    mount(Comp);
    expect(currentPayload()).toMatchObject({ name: "v1" });

    source.value = { "@type": "WebSite", name: "v2" };
    await nextTick();
    // Exactly one script with the id; text replaced.
    const all = document.querySelectorAll(`#${SCRIPT_ID}`);
    expect(all.length).toBe(1);
    expect(currentPayload()).toMatchObject({ name: "v2" });
  });

  it("removes the script when the component unmounts", () => {
    const source = ref<object | null>({ "@type": "WebSite", name: "goodbye" });
    const Comp = defineComponent({
      setup() {
        useJsonLd(source);
        return () => h("div");
      },
    });
    const wrapper = mount(Comp);
    expect(document.getElementById(SCRIPT_ID)).not.toBeNull();
    wrapper.unmount();
    expect(document.getElementById(SCRIPT_ID)).toBeNull();
  });

  it("removes the script when the source is set back to null", async () => {
    const source = ref<object | null>({ "@type": "WebSite", name: "transient" });
    const Comp = defineComponent({
      setup() {
        useJsonLd(source);
        return () => h("div");
      },
    });
    mount(Comp);
    expect(document.getElementById(SCRIPT_ID)).not.toBeNull();
    source.value = null;
    await nextTick();
    expect(document.getElementById(SCRIPT_ID)).toBeNull();
  });
});
