import { Router, type IRouter } from "express";
import healthRouter from "./health";
import dashboardRouter from "./dashboard";
import sentimentRouter from "./sentiment";
import tradesRouter from "./trades";
import stackRouter from "./stack";
import agentsRouter from "./agents";
import downloadRouter from "./download";
import toolsPageRouter from "./tools-page";
import usageRouter from "./usage";

const router: IRouter = Router();

router.use(healthRouter);
router.use(dashboardRouter);
router.use(usageRouter);
router.use(sentimentRouter);
router.use(tradesRouter);
router.use(stackRouter);
router.use(agentsRouter);
router.use(downloadRouter);
router.use(toolsPageRouter);

export default router;
