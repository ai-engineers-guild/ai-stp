// @vitest-environment jsdom
import { afterEach,beforeEach,expect,it,vi } from "vitest";
import { cleanup,fireEvent,render,screen,waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import CatalogPage from "./pages/CatalogPage";
import * as transport from "./transport";
vi.mock("./transport", async original => ({
  ...(await original<typeof import("./transport")>()),
  cmdMachineHelp:vi.fn(),cmdCatalogSearch:vi.fn(),cmdCatalogShow:vi.fn(),
  cmdSetupAcquisitionPlan:vi.fn(),cmdSetupAcquisitionApply:vi.fn(),
}));
const digest="sha256:"+"a".repeat(64);
const setup="setup_01ARZ3NDEKTSV4RRFFQ69G5FAV";
const ok=(data:Record<string,unknown>)=>({ok:true,data,error:null,error_code:null,warnings:[],continuations:[]});
const plan={schema_version:1,state_parent:{display:"local library",utf8_base64:btoa("/original library")},operation:{
  action:"catalog.setup.acquire",endpoint:"https://catalog.example",setup:{passport_digest:digest,passport:{stable_id:setup,version:"1.0"}},components:{one:{}},
}};
beforeEach(()=>{
  vi.resetAllMocks();
  vi.mocked(transport.cmdMachineHelp).mockResolvedValue(ok({commands:[{path:["registry","search"],parameters:[{name:"kind",choices:["setup"]}]}]}));
  vi.mocked(transport.cmdCatalogSearch).mockResolvedValue(ok({items:[{stable_id:setup,latest_name:"Exact fixture",latest_version:"1.0",latest_harness_id:"codex"}],next_cursor:null}));
  vi.mocked(transport.cmdCatalogShow).mockResolvedValue(ok({summary:{stable_id:setup,latest_name:"Exact fixture",latest_harness_id:"codex"},versions:[{version:"1.0",passport_digest:digest,lifecycle:"active"}]}));
  vi.mocked(transport.cmdSetupAcquisitionPlan).mockResolvedValue(ok({plan,plan_digest:digest}));
  vi.mocked(transport.cmdSetupAcquisitionApply).mockResolvedValue(ok({acquired:true}));
});
afterEach(cleanup);
async function choose() {
  render(<MemoryRouter><CatalogPage/></MemoryRouter>);
  await waitFor(()=>expect((screen.getByRole("button",{name:/Search/}) as HTMLButtonElement).disabled).toBe(false));
  fireEvent.click(screen.getByRole("button",{name:/Search/}));
  fireEvent.click(await screen.findByRole("button",{name:/Exact fixture/}));
  fireEvent.click(await screen.findByRole("button",{name:"Download exact graph"}));
}
it("downloads only the exact selected graph and opens native configuration after approval",async()=>{
  await choose();
  const checkbox=await screen.findByRole("checkbox",{name:/Download this exact graph/});
  expect(transport.cmdSetupAcquisitionApply).not.toHaveBeenCalled();
  fireEvent.click(checkbox);
  fireEvent.click(screen.getByRole("button",{name:"Download reviewed graph"}));
  await waitFor(()=>expect(transport.cmdSetupAcquisitionApply).toHaveBeenCalledWith(plan,digest,true));
  const link=await screen.findByRole("link",{name:"Configure downloaded setup"});
  expect(link.getAttribute("href")).toContain("/targets?");
  expect(link.getAttribute("href")).toContain(setup);
});
it("refuses a catalog plan that substitutes another immutable passport",async()=>{
  vi.mocked(transport.cmdSetupAcquisitionPlan).mockResolvedValue(ok({plan:{...plan,operation:{...plan.operation,setup:{...plan.operation.setup,passport_digest:"sha256:"+"b".repeat(64)}}},plan_digest:digest}));
  await choose();
  await screen.findByText(/graph differs from the exact catalog selection/);
  expect(screen.queryByRole("button",{name:"Download reviewed graph"})).toBeNull();
  expect(transport.cmdSetupAcquisitionApply).not.toHaveBeenCalled();
});
