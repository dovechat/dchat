




router = APIRouter(
    tags=["Tariffs"],
    prefix="/tariffs",
    dependencies=[Depends(auth_scheme)]
)


# === TARIFF ENDPOINTS ===

@tariff_router.get("/", response_model=list[TariffResponse])
async def get_tariffs(
    current_user: UserContext = Depends(get_current_user),
    billing_service: BillingService = Depends(get_billing_service)
) -> list[TariffResponse]:
    """Get all active tariffs"""
    return await billing_service.get_tariffs()


@tariff_router.post("/", response_model=TariffResponse, status_code=status.HTTP_201_CREATED)
async def create_tariff(
    data: TariffCreate,
    current_user: UserContext = Depends(get_current_user),
    billing_service: BillingService = Depends(get_billing_service)
) -> TariffResponse:
    """Create new tariff (admin only)"""
    return await billing_service.create_tariff(data)


@tariff_router.patch("/{tariff_id}", response_model=TariffResponse)
async def update_tariff(
    tariff_id: uuid.UUID,
    data: TariffUpdate,
    current_user: UserContext = Depends(get_current_user),
    billing_service: BillingService = Depends(get_billing_service)
) -> TariffResponse:
    """Update tariff (admin only)"""
    return await billing_service.update_tariff(tariff_id, data)
