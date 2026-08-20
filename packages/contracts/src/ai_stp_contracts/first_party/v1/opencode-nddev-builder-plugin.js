export const NddevBuilderPlugin = async ({ client }) => {
  return {
    event: async ({ event }) => {
      if (event.type === "session.created") {
        await client.app.log({
          body: {
            service: "nddev-builder",
            level: "info",
            message: "NDDev builder native projection is available",
          },
        })
      }
    },
  }
}
