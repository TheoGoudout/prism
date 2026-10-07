import { ErrorPage } from "./ErrorPage"

const ErrorComponent = () => (
  <ErrorPage
    code="Error"
    message="Something went wrong. Please try again."
    action="Go Home"
    testId="error-component"
  />
)

export default ErrorComponent
