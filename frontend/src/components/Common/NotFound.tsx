import { ErrorPage } from "./ErrorPage"

const NotFound = () => (
  <ErrorPage
    code="404"
    message="The page you are looking for was not found."
    action="Go Back"
    testId="not-found"
  />
)

export default NotFound
