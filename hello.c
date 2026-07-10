
#include <stdint.h>
#include <stdbool.h>
#include "inc/hw_memmap.h"
#include "driverlib/fpu.h"
#include "driverlib/sysctl.h"
#include "driverlib/rom.h"
#include "driverlib/pin_map.h"
#include "driverlib/uart.h"
#include "grlib/grlib.h"
#include "drivers/cfal96x64x16.h"
#include "utils/uartstdio.h"
#include "driverlib/gpio.h"


extern unsigned int num_1();
extern unsigned int num_2();
extern unsigned int num_3();
extern unsigned int num_4();
extern unsigned int Switch_Input();
extern unsigned int Switch_Init();

extern unsigned int LED_Init();
extern unsigned int LED_On();
extern unsigned int LED_Off();

extern unsigned int Blink_slow();
extern unsigned int Blink_fast();


#ifdef DEBUG
void
__error__(char *pcFilename, uint32_t ui32Line)
{
}
#endif

//*****************************************************************************
//
// Configure the UART and its pins.  This must be called before UARTprintf().
//
//*****************************************************************************
void
ConfigureUART(void)
{
    //
    // Enable the GPIO Peripheral used by the UART.
    //
    ROM_SysCtlPeripheralEnable(SYSCTL_PERIPH_GPIOA);

    //
    // Enable UART0
    //
    ROM_SysCtlPeripheralEnable(SYSCTL_PERIPH_UART0);

    //
    // Configure GPIO Pins for UART mode.
    //
    ROM_GPIOPinConfigure(GPIO_PA0_U0RX);
    ROM_GPIOPinConfigure(GPIO_PA1_U0TX);
    ROM_GPIOPinTypeUART(GPIO_PORTA_BASE, GPIO_PIN_0 | GPIO_PIN_1);

    //
    // Use the internal 16MHz oscillator as the UART clock source.
    //
    UARTClockSourceSet(UART0_BASE, UART_CLOCK_PIOSC);

    //
    // Initialize the UART for console I/O.
    //
    UARTStdioConfig(0, 115200, 16000000);
}

int main(void)
{
    ROM_FPULazyStackingEnable();
    ROM_SysCtlClockSet(SYSCTL_SYSDIV_4 | SYSCTL_USE_PLL | SYSCTL_XTAL_16MHZ |
                       SYSCTL_OSC_MAIN);
    ConfigureUART();

    UARTprintf("Hello, world!\n");

    CFAL96x64x16Init();

//*****************************************************************************************
//*****************************************************************************************

       unsigned char num = '0';

        Switch_Init();
        LED_Init();

        while(1){
        	do{
        		Switch_Input();
                num = num_1();
            } while(num == 'A');
            if (num == 'B') {
                LED_On();
            }
            else if (num == 'C') {
                LED_Off();
            }
            else if (num == 'D') {
            	Blink_slow();
            }
            else if (num == 'E') {
            	Blink_fast();
            }
            SysCtlDelay(8000000 / 3);
        }   //end while

}      //end main



