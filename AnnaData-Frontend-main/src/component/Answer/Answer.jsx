import React, { useMemo } from "react";
import Markdown from "markdown-to-jsx";
import {
  answerDeclinesRegisteredDose,
  paragraphCarriesRefusal,
} from "./refusal";

/**
 * The answer surface.
 *
 * This is the most-looked-at rectangle in the product and it was the least
 * designed: an unstyled <Markdown> in the middle of Main.jsx. Pulling it out
 * into its own component is not tidiness - it is so the markdown overrides
 * below have somewhere to live that is nowhere near Main.jsx's microphone and
 * speech handlers.
 *
 * Everything here is driven by the shape of answers the backend actually
 * returns, read off real replies rather than imagined. That shape is:
 *
 *   ### A section heading
 *   *   **Propiconazole 25% EC:** 500 मिली दवा को 750 लीटर पानी में...
 *   *   **Chhindwara:** Rs 5,952/quintal
 *
 * A dose and a price are the same markdown: a bolded label, a colon, a value.
 * That is a lucky and useful fact, because it means the two things a farmer
 * reads most carefully can be made unmistakable by one structural rule that
 * needs no language detection and no guessing at content. `FactRow` below is
 * that rule.
 *
 * The third shape, a refusal, is the one that is not structural, and `refusal.js`
 * explains at length how it is found and what that costs.
 */

/*
 * Join class names, dropping the falsy ones.
 *
 * Worth its own function only because of the bug it exists to stop repeating:
 * markdown-to-jsx passes its own `className` down to an overridden component,
 * so writing `<li className="fact-row" {...rest}>` silently loses the class to
 * the spread. Every override here takes className out of the props explicitly
 * and merges it.
 */
function cx(...names) {
  return names.filter(Boolean).join(" ") || undefined;
}

/** Flatten a React subtree to its text, for pattern tests. */
function textOf(node) {
  if (node == null || typeof node === "boolean") return "";
  if (typeof node === "string" || typeof node === "number") return String(node);
  if (Array.isArray(node)) return node.map(textOf).join("");
  if (React.isValidElement(node)) return textOf(node.props.children);
  return "";
}

/*
 * A rupee figure. Deliberately the only thing in an answer that gets picked out
 * of running text, because a mandi rate is the one value a farmer is going to
 * hunt for and a page where five things are emphasised emphasises nothing.
 *
 * Nothing similar is done for dose quantities. "500 मिली को 750 लीटर पानी में"
 * would need a units pattern per script, and getting that subtly wrong on a
 * pesticide quantity is a worse outcome than leaving it as plain text. The dose
 * gets its legibility from the row it sits in instead.
 */
const RUPEES = /((?:₹|Rs\.?|INR)\s?[\d,]+(?:\.\d+)?)/gi;

function highlightFigures(children, depth = 0) {
  if (depth > 3) return children;
  return React.Children.map(children, (child, i) => {
    if (typeof child === "string") {
      const parts = child.split(RUPEES);
      if (parts.length === 1) return child;
      // String.split with one capturing group puts the captures at odd indices.
      return parts.map((part, j) =>
        j % 2 === 1 ? (
          <b className="prose-figure" key={`${i}-${j}`}>
            {part}
          </b>
        ) : (
          part
        )
      );
    }
    if (React.isValidElement(child) && child.props && child.props.children) {
      return React.cloneElement(
        child,
        undefined,
        highlightFigures(child.props.children, depth + 1)
      );
    }
    return child;
  });
}

/**
 * Unwrap a list item that markdown put a paragraph inside.
 *
 * Markdown has two kinds of list. A "tight" list, with no blank lines between
 * the items, puts the item content straight into the <li>. A "loose" one, with
 * blank lines, wraps each item content in a <p> first. The agent writes both,
 * in the same answer and for the same kind of content - which shape you get
 * depends on how the model happened to lay out that particular reply.
 *
 * This cost an hour: the fact rows below worked against a saved answer and did
 * nothing in the browser, because the saved answer was tight and the live one
 * was loose, and a <p> is not a <strong>.
 *
 * Only a single wrapping paragraph is unwrapped. An item with two paragraphs in
 * it is prose, not a labelled fact, and is left alone.
 */
function unwrapSoleParagraph(kids) {
  if (kids.length !== 1) return kids;
  const only = kids[0];
  if (!React.isValidElement(only)) return kids;
  const isParagraph =
    only.type === "p" || (only.type && only.type.isProseParagraph);
  if (!isParagraph) return kids;
  return React.Children.toArray(only.props.children);
}

/*
 * Drop the colon the model writes inside the bold run.
 *
 * "**Propiconazole 25% EC:**" is a sentence with a colon in it. Once the label
 * is on its own line in its own row the colon is dangling punctuation, so it
 * goes. It has to be taken off the LAST text leaf rather than off the string,
 * because markdown-to-jsx hands over an array whenever the label contains any
 * markup at all - and a chemical name like "Azoxystrobin 11% + Tebuconazole
 * 18.3% w/w SC" often does.
 */
function stripTrailingColon(node) {
  if (typeof node === "string") return node.replace(/\s*[:：]\s*$/, "");
  if (Array.isArray(node)) {
    const out = node.slice();
    for (let i = out.length - 1; i >= 0; i -= 1) {
      if (typeof out[i] === "string" && out[i].trim() === "") continue;
      out[i] = stripTrailingColon(out[i]);
      break;
    }
    return out;
  }
  if (React.isValidElement(node)) {
    return React.cloneElement(
      node,
      undefined,
      stripTrailingColon(node.props.children)
    );
  }
  return node;
}

/**
 * A list item, and if it is a labelled one, a fact row.
 *
 * `*   **Tebuconazole 25% WG:** 0.750 किलोग्राम...` is a chemical and its dose.
 * `*   **Chhindwara:** Rs 5,952/quintal` is a mandi and its rate. Both were
 * rendering as a bullet with a bold run at the front, so eight APMC rates were
 * eight near-identical grey lines and the reader had to parse each one to find
 * the number.
 *
 * Split at the bold label and the two halves can be laid out: label above value
 * on a narrow screen, side by side once there is room. A plain bullet - most of
 * the "other precautions" advice - is left exactly as it was.
 */
function ListItem({ children, className, ...rest }) {
  const kids = unwrapSoleParagraph(React.Children.toArray(children));
  const first = kids[0];
  const labelled = React.isValidElement(first) && first.type === "strong";

  if (!labelled) {
    return (
      <li className={className} {...rest}>
        {highlightFigures(children)}
      </li>
    );
  }

  const label = stripTrailingColon(first.props.children);

  const value = kids.slice(1);
  const empty = textOf(value).trim() === "";

  return (
    <li className={cx("fact-row", className)} {...rest}>
      <span className="fact-label">{label}</span>
      {!empty && <span className="fact-value">{highlightFigures(value)}</span>}
    </li>
  );
}

/**
 * A paragraph, and if it is the refusal, the refusal.
 *
 * `isRefusal` is decided once for the whole answer and closed over, because the
 * signals are not reliably all in one paragraph - see refusal.js.
 *
 * No words are added. The paragraph already says, in the farmer's own language,
 * that nothing is registered for this crop and pest and that they should ask
 * their KVK. An English caption stuck on top of a Hindi sentence would help
 * nobody who needed it. All this does is make the sentence impossible to skim
 * past, in the register's own colour, with no red and no warning icon - it is
 * the system working, not failing.
 */
function makeParagraph(isRefusal) {
  function Paragraph({ children, className, ...rest }) {
    const refusal = isRefusal && paragraphCarriesRefusal(textOf(children));
    return (
      <p className={cx(refusal && "prose-refusal", className)} {...rest}>
        {highlightFigures(children)}
      </p>
    );
  }
  // How ListItem recognises the paragraph a loose list wraps its items in.
  // Once `p` is overridden, that wrapper is this component and not a "p".
  Paragraph.isProseParagraph = true;
  return Paragraph;
}

/**
 * A table in its own scroll box.
 *
 * The previous fix set `display: block; overflow-x: auto` on the table itself,
 * which did stop a wide price table from widening the whole page - the bug it
 * was written for, and it must keep working. The cost is that a table that is
 * no longer a table for layout purposes cannot size its own columns. Wrapping
 * it instead gets the same containment back with real table layout.
 */
function Table({ children, ...rest }) {
  return (
    <div className="prose-table-wrap">
      <table {...rest}>{children}</table>
    </div>
  );
}

/**
 * @param markdown    the answer, as the agent wrote it
 * @param doseStatus  the backend's own verdict, when it sends one:
 *                    "available" | "none_registered" | "not_applicable"
 */
function Answer({ markdown, doseStatus }) {
  const options = useMemo(() => {
    // The flag wins whenever it is there. It is decided where the register was
    // actually consulted, so it needs no patterns and cannot be wrong about a
    // script nobody has tested. The prose test in refusal.js stays as the
    // fallback for a deployed backend that predates the flag.
    const isRefusal = doseStatus
      ? doseStatus === "none_registered"
      : answerDeclinesRegisteredDose(markdown);
    return {
      // markdown-to-jsx will otherwise let an answer emit arbitrary HTML.
      disableParsingRawHTML: true,
      overrides: {
        p: { component: makeParagraph(isRefusal) },
        li: { component: ListItem },
        table: { component: Table },
      },
    };
  }, [markdown, doseStatus]);

  return (
    <div className="prose-answer">
      <Markdown options={options}>{markdown || ""}</Markdown>
    </div>
  );
}

export default Answer;
