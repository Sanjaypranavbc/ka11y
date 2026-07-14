import { Card } from "@/components/ui/Card";
import { pageFindings } from "@/lib/dashboardData";

const COLUMNS = [
  "Page Name",
  "URL",
  "Score",
  "Findings",
  "Violations",
  "Needs Review",
  "Passes",
] as const;

export function FindingsTable() {
  return (
    <Card>
      <h2 className="text-[18px] font-medium leading-[26px] text-gray-100">
        Findings by Page
      </h2>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[640px] border-collapse text-left">
          <thead>
            <tr className="border-b border-gray-40">
              {COLUMNS.map((col) => (
                <th
                  key={col}
                  scope="col"
                  className="whitespace-nowrap px-3 py-4 text-[16px] font-medium leading-[26px] text-gray-100"
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pageFindings.map((row) => (
              <tr key={row.url} className="border-b border-gray-40 last:border-0">
                <td className="px-3 py-4 text-[16px] leading-6 text-gray-80">{row.pageName}</td>
                <td className="px-3 py-4 text-[16px] leading-6 text-gray-80">
                  <a
                    href={row.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="hover:text-brand-teal hover:underline"
                  >
                    {row.url}
                  </a>
                </td>
                <td className="px-3 py-4 text-[16px] leading-6 text-gray-80">{row.score}%</td>
                <td className="px-3 py-4 text-[16px] leading-6 text-gray-80">{row.findings}</td>
                <td className="px-3 py-4 text-[16px] leading-6 text-gray-80">{row.violations}</td>
                <td className="px-3 py-4 text-[16px] leading-6 text-gray-80">{row.needsReview}</td>
                <td className="px-3 py-4 text-[16px] leading-6 text-gray-80">{row.passes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
